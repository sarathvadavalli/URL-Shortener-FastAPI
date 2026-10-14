import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException

from myapp import tasks
from myapp.models.url_mapping import Click, CreationRequest, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate
from myapp.services.url_service import URLService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_MYSQL_URL"), reason="disposable MySQL required"
    ),
]


@pytest.mark.parametrize(
    "same_key,same_url", [(True, True), (False, True), (False, False), (True, False)]
)
def test_concurrent_creation_serializes(store, users, same_key, same_url):
    count = 8
    barrier = Barrier(count)
    shared_key = str(uuid4())
    user_id = users[0].id

    def run(index):
        with store() as db:
            barrier.wait(timeout=10)
            payload = URLMappingCreate(
                original_url=f"https://example.com/{0 if same_url else index}"
            )
            try:
                mapping = URLService(db).create_url(
                    payload,
                    user_id,
                    f"u:{user_id}",
                    shared_key if same_key else str(uuid4()),
                )
                return ("ok", mapping.url_id, mapping.short_code)
            except HTTPException as exc:
                return ("error", exc.status_code)

    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(run, range(count)))
    successes = [item for item in results if item[0] == "ok"]
    errors = [item for item in results if item[0] == "error"]
    if same_key and not same_url:
        assert len(successes) == 1
        assert all(item[1] == 409 for item in errors)
    else:
        assert len(successes) == count, results
        assert not errors
    expected = 1 if same_key or same_url else count
    assert len({item[1] for item in successes}) == expected
    assert len({item[2] for item in successes}) == expected
    with store() as db:
        assert db.query(URLMapping).count() == expected
        assert db.query(CreationRequest).count() == (1 if same_key else count)


def test_concurrent_click_increments(store, users):
    with store() as db:
        mapping = URLService(db).create_url(
            URLMappingCreate(original_url="https://example.com"),
            users[0].id,
            f"u:{users[0].id}",
            str(uuid4()),
        )
        mapping_id = mapping.url_id
    count = 20
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda _: tasks.record_click(mapping_id, None, None, datetime.now(UTC)),
                range(count),
            )
        )
    with store() as db:
        assert db.get(URLMapping, mapping_id).click_count == count
        assert db.query(Click).count() == count


def test_existing_custom_code_collision_retries(store, users):
    from myapp.services.url_service import url_digest

    with store() as db:
        existing = URLMapping(
            user_id=users[0].id,
            owner_key=f"u:{users[0].id}",
            url_hash=url_digest("https://example.com/old"),
            original_url="https://example.com/old",
            short_code="2",
        )
        db.add(existing)
        db.commit()
        assert existing.url_id == 1
        mapping = URLService(db).create_url(
            URLMappingCreate(original_url="https://example.com/new"),
            users[0].id,
            f"u:{users[0].id}",
            str(uuid4()),
        )
        assert mapping.url_id == 3
        assert mapping.short_code == "3"
        assert db.query(URLMapping).count() == 2
