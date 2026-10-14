"""Run `python -m myapp.maintenance` to remove expired idempotency records."""

from sqlalchemy import delete

from myapp.core.time import utcnow
from myapp.database import SessionLocal
from myapp.models.url_mapping import CreationRequest


def purge_expired_requests():
    with SessionLocal() as db:
        result = db.execute(
            delete(CreationRequest).where(CreationRequest.expires_at < utcnow())
        )
        db.commit()
        return result.rowcount


if __name__ == "__main__":
    print(f"Removed {purge_expired_requests()} expired creation requests")
