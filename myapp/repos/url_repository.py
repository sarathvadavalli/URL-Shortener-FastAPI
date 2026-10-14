from sqlalchemy import func, select
from sqlalchemy.orm import Session

from myapp.models.url_mapping import Click, URLMapping
from myapp.models.user_model import Users


class URLRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_summary(self, user: Users):
        stmt = select(
            func.count(URLMapping.url_id).label("total_urls"),
            func.sum(URLMapping.click_count).label("total_clicks"),
        ).where(URLMapping.user_id == user.id)

        return self.db.execute(stmt).first()

    def list_all(self, user: Users) -> list[URLMapping]:
        return (
            self.db.query(URLMapping)
            .filter(URLMapping.user_id == user.id)
            .order_by(URLMapping.url_id.desc())
            .all()
        )

    def get_by_id(self, url_id: int, user: Users) -> URLMapping | None:
        return (
            self.db.query(URLMapping)
            .filter(URLMapping.url_id == url_id, URLMapping.user_id == user.id)
            .first()
        )

    def activate(self, url_id: int, user: Users) -> int:
        count = (
            self.db.query(URLMapping)
            .filter((URLMapping.url_id == url_id) & (URLMapping.user_id == user.id))
            .update({"is_active": True})
        )

        self.db.commit()

        return count

    def deactivate(self, url_id: int, user: Users) -> str | None:
        mapping = (
            self.db.query(URLMapping)
            .filter((URLMapping.url_id == url_id) & (URLMapping.user_id == user.id))
            .first()
        )

        if not mapping:
            return None

        mapping.is_active = False
        self.db.commit()

        return mapping.short_code

    def get_recent_analytics(self, url_id: int, user: Users) -> list[Click] | None:
        return (
            self.db.query(Click)
            .join(URLMapping, Click.url_mapping_id == URLMapping.url_id)
            .filter(
                URLMapping.url_id == url_id,
                URLMapping.user_id == user.id,
            )
            .order_by(Click.clicked_at.desc())
            .limit(3)
            .all()
        )

    def get_analytics(self, url_id: int, user: Users) -> list[Click] | None:
        return (
            self.db.query(Click)
            .join(URLMapping, Click.url_mapping_id == URLMapping.url_id)
            .filter(
                URLMapping.url_id == url_id,
                URLMapping.user_id == user.id,
            )
            .order_by(Click.clicked_at.desc())
            .all()
        )

    def get_by_short_code(self, short_code: str) -> URLMapping | None:
        return (
            self.db.query(URLMapping)
            .filter(URLMapping.short_code == short_code)
            .first()
        )
