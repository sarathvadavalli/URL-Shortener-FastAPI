from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from myapp.models.url_mapping import CreationRequest, URLMapping
from myapp.services.url_service import URLService
from tests.conftest import create, form, login_as


def mappings(store):
    with store() as db:
        return db.scalars(
            select(URLMapping).where(URLMapping.owner_key != "seed")
        ).all()


def test_startup_seeds_without_guest_user(client, store):
    with store() as db:
        assert db.query(URLMapping).count() == 2
        assert all(row.user_id is None for row in db.query(URLMapping))


def test_guest_creation_and_replay_200(client, store):
    key = str(uuid4())
    first = create(client, key=key)
    assert first.status_code == 200
    mapping = mappings(store)[0]
    assert mapping.user_id is None
    assert mapping.owner_key.startswith("g:")
    assert mapping.original_url == "https://example.com/path/"
    second = create(client, key=key)
    assert second.status_code == 200
    assert mapping.short_code in second.text
    assert len(mappings(store)) == 1
    # Each result offers a NEW operation key rather than reusing the submitted key.
    assert f'value="{key}"' not in second.text


def test_user_creation_ownership_and_distinct_ids(client, users, store):
    login_as(client, users[0])
    assert create(client, "https://example.com/one").status_code == 200
    assert create(client, "https://example.com/two").status_code == 200
    rows = mappings(store)
    assert len({row.url_id for row in rows}) == 2
    assert len({row.short_code for row in rows}) == 2
    assert all(row.user_id == users[0].id for row in rows)


def test_duplicate_url_reuses_code_per_owner(client, users, store):
    login_as(client, users[0])
    assert create(client).status_code == 200
    assert create(client).status_code == 200
    login_as(client, users[1])
    assert create(client).status_code == 200
    assert len(mappings(store)) == 2


def test_key_payload_conflict_is_409(client, store):
    key = str(uuid4())
    assert create(client, key=key).status_code == 200
    assert create(client, "https://example.com/different", key=key).status_code == 409
    assert len(mappings(store)) == 1


def test_same_key_scoped_to_different_users(client, users, store):
    key = str(uuid4())
    for user in users:
        login_as(client, user)
        assert create(client, key=key).status_code == 200
    assert len(mappings(store)) == 2


def test_guest_sessions_are_separate(client, store):
    key = str(uuid4())
    assert create(client, key=key).status_code == 200
    client.cookies.clear()
    assert create(client, key=key).status_code == 200
    assert len(mappings(store)) == 2


@pytest.mark.parametrize("key", ["not-a-uuid", "123", ""])
def test_invalid_key_is_422_without_writes(client, store, key):
    assert create(client, key=key).status_code == 422
    assert mappings(store) == []
    with store() as db:
        assert db.query(CreationRequest).count() == 0


def test_uuid_representations_normalize(client, store):
    key = uuid4()
    assert create(client, key=str(key).upper()).status_code == 200
    assert create(client, key=key.hex).status_code == 200
    with store() as db:
        entry = db.query(CreationRequest).one()
        assert entry.request_key == str(UUID(str(key)))
    assert len(mappings(store)) == 1


def test_expired_key_can_be_reused(client, store):
    key = str(uuid4())
    assert create(client, key=key).status_code == 200
    with store() as db:
        entry = db.query(CreationRequest).one()
        assert 290 < (entry.expires_at - datetime.utcnow()).total_seconds() <= 300
        entry.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert create(client, "https://example.com/new", key=key).status_code == 200
    assert len(mappings(store)) == 2


def test_failed_creation_does_not_commit_ledger(client, store, monkeypatch):
    def fail(*_):
        raise RuntimeError("injected")

    monkeypatch.setattr(URLService, "_create_mapping", fail)
    with pytest.raises(RuntimeError):
        create(client)
    with store() as db:
        assert db.query(CreationRequest).count() == 0
        assert mappings(store) == []


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


def test_preserves_slashes_query_and_fragment(client, store):
    url = "https://example.com/path/?next=/target/#fragment/"
    assert create(client, url).status_code == 200
    assert mappings(store)[0].original_url == url


def test_missing_form_and_json_body_rejected(client):
    fields = form(client)
    assert client.post("/urls", data=fields).status_code == 422
    assert (
        client.post(
            "/urls",
            json={"original_url": "https://example.com"},
            headers={"x-csrf-token": fields["csrf_token"]},
        ).status_code
        == 422
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


def test_output_escaping(client):
    url = 'https://example.com/?q=<script>alert(1)</script>&x="onclick="alert(2)'
    response = create(client, url)
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&amp;x=" in response.text
