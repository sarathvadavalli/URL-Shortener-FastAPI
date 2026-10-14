import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from myapp.core import security
from myapp.core.config import Settings, settings
from myapp.models.url_mapping import URLMapping
from myapp.models.user_model import Users
from myapp.schemas.auth_user import UserCreate
from tests.conftest import create, form, login_as


def signed(payload, header=None):
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    head, body = enc(header if header is not None else {"alg": "HS256"}), enc(payload)
    message = f"{head}.{body}"
    sig = hmac.new(
        settings.jwt_secret_key.encode(), message.encode(), hashlib.sha256
    ).digest()
    return message + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"sub": []},
        {"sub": "", "exp": 9999999999},
        {"sub": "alice", "exp": "9999999999"},
        {"sub": "alice", "exp": True},
        {"sub": "alice", "exp": 0},
    ],
)
def test_bad_claims_rejected(payload):
    with pytest.raises(ValueError):
        security.decode_access_token(signed(payload))


@pytest.mark.parametrize("header", [[], None, {"alg": "none"}, {"alg": "HS512"}])
def test_bad_header_rejected(header):
    if header is None:
        token = signed({"sub": "alice", "exp": 9999999999}, {"alg": None})
    else:
        token = signed({"sub": "alice", "exp": 9999999999}, header)
    with pytest.raises(ValueError):
        security.decode_access_token(token)


@pytest.mark.parametrize("token", ["abc", "a.b.c", "!!.!!.!!", "null.null.null"])
def test_malformed_cookie_returns_401(client, token):
    client.cookies.set("access_token", token)
    assert client.get("/urls").status_code == 401


def test_expiration_equality_rejected(monkeypatch):
    class Clock:
        @staticmethod
        def now(_):
            return datetime.fromtimestamp(100, UTC)

    monkeypatch.setattr(security, "datetime", Clock)
    for exp in (99, 100):
        with pytest.raises(ValueError):
            security.decode_access_token(signed({"sub": "alice", "exp": exp}))
    assert (
        security.decode_access_token(signed({"sub": "alice", "exp": 101}))["sub"]
        == "alice"
    )


def test_password_hash_salt_and_verification():
    first, second = security.hash_password("correct"), security.hash_password("correct")
    assert first != second
    assert security.verify_password("correct", first)
    assert not security.verify_password("wrong", first)
    assert not security.verify_password("correct", "pbkdf2_sha256$-1$%%%$x")


def test_jwt_algorithm_config_rejected():
    with pytest.raises(ValidationError):
        Settings(jwt_algorithm="HS512")


def test_register_login_and_logout(client, store, monkeypatch):
    fields = form(client)
    headers = {"x-csrf-token": fields["csrf_token"]}
    payload = dict(
        first_name=" Alice ",
        last_name=" Test ",
        username="Alice_one",
        email="Alice@example.com",
        password="password123",
    )
    assert (
        client.post("/auth/register", json=payload, headers=headers).status_code == 201
    )
    assert (
        client.post("/auth/register", json=payload, headers=headers).status_code == 409
    )
    with store() as db:
        user = db.query(Users).one()
        assert user.user_name == "alice_one"
        assert user.first_name == "Alice"
        assert security.verify_password("password123", user.password)
    response = client.post(
        "/auth/login",
        json={"identifier": " ALICE@EXAMPLE.COM ", "password": "password123"},
        headers=headers,
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Max-Age=3600" in cookie
    assert client.get("/home").status_code == 200
    # Login rotated the CSRF token. Old token no longer mutates the session.
    assert client.post("/auth/logout", headers=headers).status_code == 403
    headers = {"x-csrf-token": form(client)["csrf_token"]}
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/home").status_code == 401


@pytest.mark.parametrize("has_mx,status", [(False, 422), (None, 503)])
def test_registration_mx_failure(client, store, monkeypatch, has_mx, status):
    from myapp.routers import auth_router

    monkeypatch.setattr(auth_router, "domain_has_mx_record", lambda _: has_mx)
    response = client.post(
        "/auth/register",
        json=dict(
            first_name="A",
            last_name="B",
            username="abc",
            email="abc@example.com",
            password="secret1",
        ),
        headers={"x-csrf-token": form(client)["csrf_token"]},
    )
    assert response.status_code == status
    with store() as db:
        assert db.query(Users).count() == 0


@pytest.mark.parametrize("name", ["abc_def", "abc-def", "abc123"])
def test_username_policy(name):
    assert (
        UserCreate(
            first_name="A",
            last_name="B",
            username=name,
            email="a@example.com",
            password="secret1",
        ).username
        == name
    )


@pytest.mark.parametrize(
    "name",
    [
        "ab",
        "abcdefghijklmnopq",
        "_abc",
        "abc-",
        "abc__def",
        "abc--def",
        "abc_-def",
        "abc-_def",
        "अbc",
    ],
)
def test_invalid_username(name):
    with pytest.raises(ValidationError):
        UserCreate(
            first_name="A",
            last_name="B",
            username=name,
            email="a@example.com",
            password="secret1",
        )


@pytest.mark.parametrize(
    "path", ["/home", "/urls", "/urls/123", "/urls/123/analytics/view"]
)
def test_unauthenticated_json_vs_html(client, path):
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"accept": "text/html"})
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_ownership_detail_analytics_and_state(client, users, store):
    login_as(client, users[0])
    create(client)
    with store() as db:
        mapping = db.query(URLMapping).filter_by(user_id=users[0].id).one()
    assert client.get(f"/urls/{mapping.url_id}/analytics/view").status_code == 200
    login_as(client, users[1])
    for path in (
        f"/urls/{mapping.url_id}",
        f"/urls/{mapping.url_id}/analytics/view",
        "/urls/999999/analytics/view",
    ):
        assert client.get(path).status_code == 404
    for action in ("activate", "deactivate"):
        assert (
            client.post(
                f"/urls/{mapping.url_id}/{action}",
                data={"csrf_token": form(client)["csrf_token"]},
            ).status_code
            == 404
        )
    assert mapping.original_url not in client.get("/urls").text
    with store() as db:
        assert db.get(URLMapping, mapping.url_id).is_active


def test_csrf_blocks_mutations(client, users, store):
    assert (
        client.post(
            "/urls",
            data={"original_url": "https://example.com", "idempotency_key": "bad"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/auth/login", json={"identifier": "alice", "password": "password123"}
        ).status_code
        == 403
    )
    login_as(client, users[0])
    assert (
        client.post("/urls/123/deactivate", data={"csrf_token": "wrong"}).status_code
        == 403
    )


def test_stale_cookie_create_returns_auth_error(client):
    fields = form(client)
    client.cookies.set("access_token", "bad")
    assert client.get("/urls/create").status_code == 401
    assert (
        client.post(
            "/urls", data={**fields, "original_url": "https://example.com"}
        ).status_code
        == 401
    )


def test_non_ascii_token_parser():
    with pytest.raises(ValueError):
        security.decode_access_token("e30.☃.x")


def test_unicode_csrf_rejected(client):
    fields = form(client)
    fields["csrf_token"] = "☃"
    assert (
        client.post(
            "/urls", data={**fields, "original_url": "https://example.com"}
        ).status_code
        == 403
    )
