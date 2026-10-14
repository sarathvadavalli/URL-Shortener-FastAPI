import json
import os

import pytest
import redis

from myapp.models.url_mapping import URLMapping
from myapp.services import url_service
from tests.conftest import create, form, login_as

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_REDIS_URL"), reason="disposable Redis required"
    ),
]


def test_real_redis_ttl_expiry_deactivation_and_stale_refill(
    client, users, store, monkeypatch
):
    connection = redis.from_url(os.environ["TEST_REDIS_URL"], decode_responses=True)
    monkeypatch.setattr(url_service, "redis_client", connection)
    login_as(client, users[0])
    create(client)
    with store() as db:
        mapping = db.query(URLMapping).filter_by(user_id=users[0].id).one()
    key = "url:" + mapping.short_code
    connection.delete(key)
    try:
        assert client.get("/" + mapping.short_code).status_code == 307
        assert 0 < connection.ttl(key) <= 3600
        assert json.loads(connection.get(key))["original_url"] == mapping.original_url
        assert client.get("/" + mapping.short_code).status_code == 307
        connection.expire(key, 0)
        assert connection.get(key) is None
        assert client.get("/" + mapping.short_code).status_code == 307
        assert 0 < connection.ttl(key) <= 3600
        assert (
            client.post(
                f"/urls/{mapping.url_id}/deactivate",
                data={"csrf_token": form(client)["csrf_token"]},
            ).status_code
            == 303
        )
        assert connection.get(key) is None
        connection.set(
            key,
            json.dumps(
                {"url_mapping_id": mapping.url_id, "original_url": mapping.original_url}
            ),
            ex=3600,
        )
        assert client.get("/" + mapping.short_code).status_code == 404
        assert connection.get(key) is None
    finally:
        connection.delete(key)
        connection.close()
