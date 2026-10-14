import hashlib
import json
import logging
from datetime import timedelta

from fastapi import HTTPException
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from myapp.core.time import utcnow
from myapp.database import redis_client
from myapp.models.url_mapping import CreationRequest, URLMapping
from myapp.repos.url_repository import URLRepository

logger = logging.getLogger(__name__)


def url_digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class URLService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = URLRepository(db)

    @staticmethod
    def _generate_short_code(value: int) -> str:
        if value < 0:
            raise ValueError("value must be non-negative")
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if value == 0:
            return "0"
        encoded = []
        while value:
            value, remainder = divmod(value, 62)
            encoded.append(alphabet[remainder])
        return "".join(reversed(encoded))

    def _create_mapping(self, original_url, user_id, owner_key):
        digest = url_digest(original_url)
        existing = (
            self.db.query(URLMapping)
            .filter_by(owner_key=owner_key, url_hash=digest)
            .first()
        )
        if existing:
            if existing.original_url != original_url:
                raise HTTPException(409, "URL fingerprint conflict")
            return existing
        # Database allocation works across processes; a savepoint isolates races.
        for _ in range(3):
            try:
                with self.db.begin_nested():
                    mapping = URLMapping(
                        user_id=user_id,
                        owner_key=owner_key,
                        url_hash=digest,
                        original_url=original_url,
                    )
                    self.db.add(mapping)
                    self.db.flush()
                    mapping.short_code = self._generate_short_code(mapping.url_id)
                    self.db.flush()
                return mapping
            except IntegrityError:
                # Locking read sees the winner under MySQL REPEATABLE READ.
                existing = (
                    self.db.query(URLMapping)
                    .filter_by(
                        owner_key=owner_key,
                        url_hash=digest,
                    )
                    .with_for_update()
                    .first()
                )
                if existing:
                    if existing.original_url != original_url:
                        raise HTTPException(409, "URL fingerprint conflict")
                    return existing
                # An existing custom/seed code may match this ID's Base62 code.
        raise HTTPException(503, "Unable to allocate a short code; please retry")

    def create_url(self, payload, user_id, owner_key, request_key):
        original_url = str(payload.original_url)
        digest = url_digest(original_url)
        # A duplicate ledger insert waits for the winning DB transaction to commit.
        # Deadlocks/lock timeouts receive bounded retries, using fresh transactions.
        for attempt in range(3):
            try:
                now = utcnow()
                try:
                    with self.db.begin_nested():
                        entry = CreationRequest(
                            owner_key=owner_key,
                            request_key=request_key,
                            payload_hash=digest,
                            expires_at=now + timedelta(seconds=300),
                        )
                        self.db.add(entry)
                        self.db.flush()
                except IntegrityError:
                    entry = (
                        self.db.query(CreationRequest)
                        .filter_by(
                            owner_key=owner_key,
                            request_key=request_key,
                        )
                        .with_for_update()
                        .one_or_none()
                    )
                    if entry is None:
                        # An expired entry may have been removed by maintenance.
                        self.db.rollback()
                        continue
                    if entry.expires_at > now:
                        if entry.payload_hash != digest:
                            raise HTTPException(
                                409, "Idempotency key was used for a different URL"
                            )
                        mapping = (
                            self.db.query(URLMapping)
                            .filter_by(url_id=entry.url_mapping_id)
                            .with_for_update()
                            .first()
                        )
                        if mapping is None:
                            raise HTTPException(
                                409, "Original result is no longer available"
                            )
                        self.db.commit()
                        return mapping
                    entry.payload_hash = digest
                    entry.expires_at = now + timedelta(seconds=300)
                mapping = self._create_mapping(original_url, user_id, owner_key)
                entry.url_mapping_id = mapping.url_id
                self.db.commit()
                return mapping
            except OperationalError as exc:
                self.db.rollback()
                errno = getattr(exc.orig, "args", [None])[0]
                if errno not in (1205, 1213) or attempt == 2:
                    raise HTTPException(
                        503, "Database temporarily unavailable; please retry"
                    ) from exc
            except Exception:
                self.db.rollback()
                raise

        raise HTTPException(503, "Please retry URL creation")

    def list_urls(self, user):
        return self.repository.list_all(user)

    def get_url(self, url_id, user):
        return self.repository.get_by_id(url_id, user)

    def activate_url(self, url_id, user):
        return self.repository.activate(url_id, user)

    def deactivate_url(self, url_id, user):
        code = self.repository.deactivate(url_id, user)
        if not code:
            return False
        self._delete_cache(f"url:{code}")
        return True

    @staticmethod
    def _delete_cache(key):
        try:
            redis_client.delete(key)
        except RedisError:
            logger.warning(
                "Redis cache deletion failed; database status remains authoritative"
            )

    def get_summary(self, user):
        return self.repository.get_summary(user)

    def get_recent_analytics(self, url_id, user):
        return self.repository.get_recent_analytics(url_id, user)

    def get_analytics(self, url_id, user):
        if self.get_url(url_id, user) is None:
            return None
        return self.repository.get_analytics(url_id, user)

    def get_original_by_short_code(self, short_code):
        # Always check committed DB status. Redis alone cannot safely invalidate
        # a deactivated link when deletion fails or an in-flight read refills it.
        mapping = self.repository.get_by_short_code(short_code)
        key = f"url:{short_code}"
        if mapping is None or not mapping.is_active:
            self._delete_cache(key)
            return None
        data = {"url_mapping_id": mapping.url_id, "original_url": mapping.original_url}
        try:
            cached = redis_client.get(key)
            if cached:
                try:
                    value = json.loads(cached)
                    if isinstance(value, dict) and value == data:
                        return data
                except (ValueError, TypeError):
                    pass
            redis_client.set(key, json.dumps(data), ex=3600)
        except RedisError:
            logger.warning("Redis unavailable; resolving redirect from database")
        return data
