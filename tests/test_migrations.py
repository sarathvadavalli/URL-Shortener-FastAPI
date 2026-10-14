import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from myapp import database, main
from myapp.core.config import settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_MYSQL_URL"), reason="disposable MySQL required"
    ),
]


def legacy(store, monkeypatch):
    engine = store.kw["bind"]
    database.Base.metadata.drop_all(engine)
    monkeypatch.setattr(
        settings, "DATABASE_URL", engine.url.render_as_string(hide_password=False)
    )
    config = Config("alembic.ini")
    command.upgrade(config, "0001")
    with engine.begin() as conn:
        conn.execute(text("SET sql_mode=CONCAT(@@sql_mode, ',NO_AUTO_VALUE_ON_ZERO')"))
        for identifier, name in [(0, "legacyguest"), (1, "legacyuser")]:
            conn.execute(
                text(
                    "INSERT INTO users(id, first_name, last_name, user_name, email, password, created_at) VALUES(:id,'A','B',:name,:email,:pw,NOW())"
                ),
                {
                    "id": identifier,
                    "name": name,
                    "email": f"{name}@example.com",
                    "pw": name,
                },
            )
        conn.execute(
            text(
                "INSERT INTO url_mappings(url_id,user_id,original_url,short_code,created_at,click_count,is_active) VALUES(1234567890123,1,'https://example.com/path/','oldcode',NOW(),1,1),(1234567890124,0,'https://example.com/guest','guestcode',NOW(),0,0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO clicks(url_mapping_id,clicked_at,user_agent,ip_address) VALUES(1234567890123,NOW(),'old-agent','::1')"
            )
        )
    return config, engine


def test_migration_preserves_ids_codes_clicks_and_guests(store, monkeypatch):
    config, engine = legacy(store, monkeypatch)
    command.upgrade(config, "head")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT url_id,user_id,owner_key,short_code,click_count,is_active FROM url_mappings ORDER BY url_id"
            )
        ).all()
        assert tuple(rows[0]) == (1234567890123, 1, "u:1", "oldcode", 1, 1)
        assert tuple(rows[1]) == (
            1234567890124,
            None,
            "legacy:guest",
            "guestcode",
            0,
            0,
        )
        assert (
            conn.execute(text("SELECT user_agent FROM clicks")).scalar() == "old-agent"
        )
    assert "creation_requests" in inspect(engine).get_table_names()
    command.upgrade(config, "head")  # Idempotent upgrade via revision tracking.
    with store() as db:
        from uuid import uuid4

        from myapp.schemas.url_mapping import URLMappingCreate
        from myapp.services.url_service import URLService

        mapping = URLService(db).create_url(
            URLMappingCreate(original_url="https://example.com/after"),
            1,
            "u:1",
            str(uuid4()),
        )
        assert mapping.url_id > 1234567890124
        assert mapping.short_code not in ("oldcode", "guestcode")


def test_duplicate_preflight_preserves_legacy_schema(store, monkeypatch):
    config, engine = legacy(store, monkeypatch)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO url_mappings(user_id,original_url,short_code,created_at,click_count,is_active) VALUES(1,'https://example.com/path/','dupecode',NOW(),0,1)"
            )
        )
    with pytest.raises(RuntimeError, match="Duplicate owner/URL"):
        command.upgrade(config, "head")
    assert "owner_key" not in {
        column["name"] for column in inspect(engine).get_columns("url_mappings")
    }
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM url_mappings")).scalar() == 3
        assert conn.execute(text("SELECT COUNT(*) FROM clicks")).scalar() == 1


def test_parallel_seed_workers(store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: main.seed_url_mappings(), range(4)))
    with store() as db:
        from myapp.models.url_mapping import URLMapping

        assert db.query(URLMapping).count() == 2
