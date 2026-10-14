import logging
from datetime import UTC, datetime

from myapp.database import SessionLocal
from myapp.models.url_mapping import Click, URLMapping


def record_click(
    url_mapping_id: int,
    ip_address: str | None,
    user_agent: str | None,
    clicked_at: datetime,
):
    # MySQL DATETIME stores naive UTC; normalize an aware request timestamp.
    if clicked_at.tzinfo is not None:
        clicked_at = clicked_at.astimezone(UTC).replace(tzinfo=None)
    user_agent = user_agent[:255] if user_agent is not None else None
    ip_address = ip_address[:45] if ip_address is not None else None
    db = SessionLocal()
    try:
        click = Click(
            url_mapping_id=url_mapping_id,
            ip_address=ip_address,
            user_agent=user_agent,
            clicked_at=clicked_at,
        )

        db.add(click)

        db.query(URLMapping).filter(URLMapping.url_id == url_mapping_id).update(
            {URLMapping.click_count: URLMapping.click_count + 1}
        )

        db.commit()

    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Click persistence failed for mapping %s", url_mapping_id
        )
        raise

    finally:
        db.close()
