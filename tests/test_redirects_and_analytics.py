import json
from datetime import UTC, datetime, timedelta

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy.exc import IntegrityError

from myapp import tasks
from myapp.models.url_mapping import Click, URLMapping
from tests.conftest import create, form, login_as


def own_mapping(store, user):
    with store() as db:
        return db.query(URLMapping).filter_by(user_id=user.id).one()


def test_redirect_lifecycle_warm_cache(client, users, store, cache):
    login_as(client, users[0])
    assert create(client).status_code == 200
    mapping = own_mapping(store, users[0])
    for _ in range(2):
        response = client.get("/" + mapping.short_code)
        assert response.status_code == 307
        assert response.headers["location"] == mapping.original_url
    key = "url:" + mapping.short_code
    assert cache.ttls[key] == 3600
    with store() as db:
        assert db.get(URLMapping, mapping.url_id).click_count == 2
        assert db.query(Click).count() == 2
    for _ in range(2):
        response = client.post(
            f"/urls/{mapping.url_id}/deactivate",
            data={"csrf_token": form(client)["csrf_token"]},
        )
        assert response.status_code == 303
    assert key not in cache.data
    assert client.get("/" + mapping.short_code).status_code == 404
    response = client.get(f"/urls/{mapping.url_id}")
    assert "URL deactivated successfully" in response.text
    assert (
        "URL deactivated successfully" not in client.get(f"/urls/{mapping.url_id}").text
    )
    for _ in range(2):
        assert (
            client.post(
                f"/urls/{mapping.url_id}/activate",
                data={"csrf_token": form(client)["csrf_token"]},
            ).status_code
            == 303
        )
    assert client.get("/" + mapping.short_code).status_code == 307
    with store() as db:
        assert db.get(URLMapping, mapping.url_id).click_count == 3


def test_missing_redirect_no_click(client, store):
    assert client.get("/missing-code").status_code == 404
    with store() as db:
        assert db.query(Click).count() == 0


@pytest.mark.parametrize("failure", ["get", "set", "delete"])
def test_redis_outage_and_deactivation(
    client, users, store, cache, monkeypatch, failure
):
    login_as(client, users[0])
    create(client)
    mapping = own_mapping(store, users[0])
    key = "url:" + mapping.short_code
    assert client.get("/" + mapping.short_code).status_code == 307

    def fail(*args, **kwargs):
        raise ConnectionError("injected Redis outage")

    monkeypatch.setattr(cache, failure, fail)
    assert client.get("/" + mapping.short_code).status_code == 307
    assert (
        client.post(
            f"/urls/{mapping.url_id}/deactivate",
            data={"csrf_token": form(client)["csrf_token"]},
        ).status_code
        == 303
    )
    # Even a surviving/repopulated stale cache entry cannot bypass DB inactive state.
    cache.data[key] = json.dumps(
        {"url_mapping_id": mapping.url_id, "original_url": mapping.original_url}
    )
    assert client.get("/" + mapping.short_code).status_code == 404
    # URL creation/idempotency remains available throughout Redis failures.
    assert create(client, "https://example.com/another").status_code == 200


@pytest.mark.parametrize(
    "cached",
    [
        "not-json",
        "[]",
        "{}",
        "null",
        '{"url_mapping_id": 999, "original_url": "https://evil.example"}',
    ],
)
def test_corrupt_cache_refills_from_database(client, users, store, cache, cached):
    login_as(client, users[0])
    create(client)
    mapping = own_mapping(store, users[0])
    key = "url:" + mapping.short_code
    cache.data[key] = cached
    response = client.get("/" + mapping.short_code)
    assert response.status_code == 307
    assert response.headers["location"] == mapping.original_url
    assert json.loads(cache.data[key])["url_mapping_id"] == mapping.url_id


def test_click_atomic_rollback_and_metadata(client, users, store):
    login_as(client, users[0])
    create(client)
    mapping = own_mapping(store, users[0])
    when = datetime.now(UTC)
    tasks.record_click(mapping.url_id, "::1", "x" * 300, when)
    with store() as db:
        click = db.query(Click).one()
        assert click.ip_address == "::1"
        assert len(click.user_agent) == 255
        assert click.clicked_at == when.replace(tzinfo=None)
        assert db.get(URLMapping, mapping.url_id).click_count == 1
    with pytest.raises(IntegrityError):
        tasks.record_click(99999999, None, None, when)
    with store() as db:
        assert db.query(Click).count() == 1
        assert db.get(URLMapping, mapping.url_id).click_count == 1


def test_analytics_sort_limit_empty_and_escape(client, users, store):
    login_as(client, users[0])
    create(client)
    mapping = own_mapping(store, users[0])
    assert (
        "No click analytics"
        in client.get(f"/urls/{mapping.url_id}/analytics/view").text
    )
    for i in range(5):
        tasks.record_click(
            mapping.url_id,
            None,
            f"<script>event{i}</script>",
            datetime.now(UTC) + timedelta(seconds=i),
        )
    detail = client.get(f"/urls/{mapping.url_id}").text
    assert "event4" in detail and "event2" in detail
    assert "event1" not in detail and "event0" not in detail
    assert "<script>event4</script>" not in detail
    assert "&lt;script&gt;event4&lt;/script&gt;" in detail
    analytics = client.get(f"/urls/{mapping.url_id}/analytics/view").text
    assert (
        analytics.index("event4")
        < analytics.index("event3")
        < analytics.index("event0")
    )


@pytest.mark.parametrize("path", ["/home", "/urls", "/urls/create", "/auth/login"])
def test_no_store_headers(client, users, path):
    login_as(client, users[0])
    assert client.get(path).headers["cache-control"] == "no-store"


def test_reserved_routes_do_not_count_clicks(client, store):
    assert client.get("/").status_code == 302
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/urls/list").status_code == 401
    with store() as db:
        assert db.query(Click).count() == 0


def test_missing_update_requires_auth_and_csrf(client):
    fields = form(client)
    assert (
        client.post(
            "/urls/123/deactivate", data={"csrf_token": fields["csrf_token"]}
        ).status_code
        == 401
    )


def test_session_cookie_is_secure(client):
    response = client.get("/urls/create")
    assert "secure" in response.headers["set-cookie"].lower()
    assert "httponly" in response.headers["set-cookie"].lower()
