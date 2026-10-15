from datetime import datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from myapp.main import seed_url_mappings
from myapp.models.url_mapping import URLMapping
from myapp.models.user_model import Users
from myapp.services.url_service import URLService
from tests.conftest import create, form, login_as

# python -m pytest tests/test_url_creation.py

def mappings(store):
    with store() as db:
        records = db.scalars(
            select(URLMapping).offset(2)
        ).all()

        return records


def test_startup_seeds_without_guest_user(client, store):
    with store() as db:
        user = db.get(Users, 0)
        assert user is not None
        mappings = db.query(URLMapping)
        assert mappings.count() == 2
        assert all(row.user_id == 0 for row in mappings)


def test_guest_creation_and_replay_redirect(client, store):
    key1 = str(uuid4())
    first = create(client, key=key1)
    assert first.status_code == 200
    mapping = mappings(store)[0]
    assert mapping.user_id == 0
    assert mapping.original_url == "https://example.com/path"

    second = create(client, key=key1)
    assert second.status_code == 303
    assert second.headers["location"] == "/urls/create"
    assert len(mappings(store)) == 1

    key2 = str(uuid4())
    third = create(client, key=key2)
    assert third.status_code == 200
    assert mapping.short_code in third.text
    assert len(mappings(store)) == 1


def test_user_creation_ownership_and_distinct_ids(client, users, store):
    login_as(client, users[0])
    first = create(client, "https://example.com/one")
    assert first.status_code == 200, first.text
    second = create(client, "https://example.com/two")
    assert second.status_code == 200, second.text
    rows = mappings(store)
    assert len(rows) == 2
    assert all(row.user_id == users[0].id for row in rows)
    assert len({row.url_id for row in rows}) == 2
    assert len({row.short_code for row in rows}) == 2


def test_duplicate_url_reuses_code_per_owner(client, users, store):
    login_as(client, users[0])
    assert create(client).status_code == 200
    assert create(client).status_code == 200
    assert len(mappings(store)) == 1
    login_as(client, users[1])
    assert create(client).status_code == 200
    assert len(mappings(store)) == 2


def test_same_key_scoped_to_same_user(client, users, store):
    key = str(uuid4())
    assert create(client, key=key).status_code == 200
    replay = create(client, key=key)
    assert replay.status_code == 303
    assert replay.headers["location"] == "/urls/create"
    assert len(mappings(store)) == 1


def test_same_key_scoped_to_different_users(client, users, store):
    key = str(uuid4())
    for user in users:
        login_as(client, user)
        assert create(client, key=key).status_code == 200
    assert len(mappings(store)) == 2


def test_expired_key_can_be_reused(client, store, cache):
    key = str(uuid4())
    assert create(client, key=key).status_code == 200

    cache_key = next(reversed(cache.data))
    assert cache_key == f"idempotency:url-create:0:{key}"
    assert cache.get(cache_key) == "success"
    assert 290 < cache.expires_at[cache_key] - monotonic() <= 300
    assert create(client, key=key).status_code == 303

    cache.expires_at[cache_key] = monotonic() - 1
    assert cache.get(cache_key) is None

    response = create(client, key=key)
    assert response.status_code == 200
    assert cache.get(cache_key) == "success"
    assert len(mappings(store)) == 1


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/a",
        "javascript:alert(1)",
        "https://localhost/",
        "https://example..com/",
        "https://url-shortener-fastapi-rato.onrender.com/a",
    ],
)
def test_invalid_urls_do_not_write(client, store, url):
    assert create(client, url).status_code == 422
    assert mappings(store) == []


def test_missing_form_and_json_fields(client):
    fields = form(client)
    # Missing original_url
    assert client.post("/urls", data=fields).status_code == 422

    # Missing csrf_token
    assert (
        client.post(
            "/urls",
            data={"original_url": "https://example.com", "idempotency_key": fields["idempotency_key"]}
        ).status_code == 200
    )

    # Missing idempotency key
    assert (
        client.post(
            "/urls",
            json={"original_url": "https://example.com"},
            headers={"x-csrf-token": fields["csrf_token"]},
        ).status_code == 422
    )


@pytest.mark.parametrize(
    "value,expected",
    [(0, "0"), (1, "1"), (61, "Z"), (62, "10"), (3843, "ZZ"), (3844, "100")],
)
def test_base62(value, expected):
    assert URLService._generate_short_code(value) == expected


def test_negative_base62_rejected():
    with pytest.raises(ValueError):
        URLService._generate_short_code(-1)
