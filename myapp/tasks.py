from datetime import datetime, timezone
from fastapi import BackgroundTasks

from myapp.database import SessionLocal
from myapp.models.url_mapping import Click, URLMapping


def record_click(url_mapping_id: int, ip_address: str | None, 
    user_agent: str | None, clicked_at: datetime
):
    db = SessionLocal()
    try:
        click = Click(
            url_mapping_id=url_mapping_id,
            ip_address=ip_address,
            user_agent=user_agent,
            clicked_at=clicked_at,
        )

        db.add(click)

        db.query(URLMapping).filter(URLMapping.url_id == url_mapping_id).update({
            URLMapping.click_count: URLMapping.click_count + 1
        })

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()