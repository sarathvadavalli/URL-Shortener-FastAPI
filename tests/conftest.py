import html
import os
import re
from time import monotonic
from uuid import uuid4

# Only test configuration is loaded, before importing any application modules.
os.environ.update(
    DATABASE_URL="sqlite://",
    JWT_SECRET_KEY="test-jwt-secret",
    SESSION_SECRET_KEY="test-session-secret",
    ANONYMOUS_USER_PASSWORD="test-anonymous-password",
    COOKIE_SECURE="true",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from myapp import database, main, tasks
from myapp.core.security import create_access_token, hash_password
from myapp.core.csrf import csrf_token
from myapp.models.user_model import Users
from myapp.routers import auth_router, ui_router
from myapp.services import url_service


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}
        self.expires_at = {}

    def get(self, key):
        expires_at = self.expires_at.get(key)
        if expires_at is not None and expires_at <= monotonic():
            self.delete(key)
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttls[key] = ex
        self.expires_at[key] = monotonic() + ex if ex is not None else None
        return True

    def delete(self, key):
        self.ttls.pop(key, None)
        self.expires_at.pop(key, None)
        return int(self.data.pop(key, None) is not None)


@pytest.fixture
def store(tmp_path, monkeypatch):
    mysql_url = os.environ.get("TEST_MYSQL_URL")
    if mysql_url:
        url = make_url(mysql_url)
        if not url.database or not url.database.startswith("url_shortener_test"):
            raise RuntimeError("TEST_MYSQL_URL database must begin url_shortener_test")
        admin = create_engine(url.set(database="mysql"), isolation_level="AUTOCOMMIT")
        name = "url_shortener_test_" + uuid4().hex
        with admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
        engine = create_engine(url.set(database=name), pool_pre_ping=True)
    else:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'test.db'}",
            connect_args={"check_same_thread": False},
        )
        database.configure_sqlite_transactions(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    monkeypatch.setattr(auth_router, "domain_has_mx_record", lambda _: True)
    database.init_db()
    yield sessions
    engine.dispose()
    if mysql_url:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE `{name}`"))
        admin.dispose()


@pytest.fixture
def cache(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(url_service, "redis_client", fake)
    monkeypatch.setattr(ui_router, "redis_client", fake)
    return fake


@pytest.fixture
def client(store, cache):
    with TestClient(
        main.app, base_url="https://testserver", follow_redirects=False
    ) as client:
        yield client


@pytest.fixture
def users(store):
    with store() as db:
        result = []
        for name in ("sai01", "sarath01"):
            user = Users(
                first_name=name,
                last_name="Test",
                user_name=name,
                email=f"{name}@example.com",
                password=hash_password("password123"),
            )
            db.add(user)
            db.flush()
            result.append(user)
        db.commit()
        return result


def login_as(client, user):
    client.cookies.set("access_token", create_access_token(user.user_name))


def form(client):
    response = client.get("/urls/create")
    assert response.status_code == 200
    fields = {
        name: html.unescape(value)
        for name, value in re.findall(
            r'name="(csrf_token|idempotency_key)" value="([^"]*)"', response.text
        )
    }
    assert len(fields) == 2
    return fields


def create(client, url="https://example.com/path/", key=None):
    fields = form(client)
    if key is not None:
        fields["idempotency_key"] = key

    return client.post("/urls", data={**fields, "original_url": url})
