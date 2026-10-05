from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from myapp.models.url_mapping import Click, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate


class URLRepository:
    def __init__(self, db: Session):
        self.db = db


    # Insert followed by read approach because assuming 90% requests contain new urls and 10% existing ones
    def create(self, payload: URLMappingCreate, url_id: int, short_code: str) -> URLMapping:
        original_url = str(payload.original_url)

        mapping = URLMapping(
            url_id=url_id,
            original_url=original_url,
            short_code=short_code,
        )

        try:
            self.db.add(mapping)
            self.db.commit()

            return mapping

        except IntegrityError as e:
            # Handles duplicate original_urls and returns existing short code
            self.db.rollback()

            existing_mapping = (
                self.db.query(URLMapping)
                .filter(URLMapping.original_url == original_url)
                .first()
            )

            if existing_mapping:
                print("Returning existing mapping")
                return existing_mapping

            raise e
        except Exception as e:
            # Handles non-database exceptions (e.g: AttributeError, TypeError)
            self.db.rollback()
            print(f"Unexpected application error: {e}")
            raise e


    def list_all(self) -> list[URLMapping]:
        return self.db.query(URLMapping).order_by(URLMapping.url_id.desc()).all()


    def get_by_id(self, url_id: int) -> Optional[URLMapping]:
        return self.db.query(URLMapping).filter(URLMapping.url_id == url_id).first()


    def delete(self, url_id: int) -> bool:
        mapping = self.get_by_id(url_id)
        if mapping is None:
            return False

        self.db.delete(mapping)
        self.db.commit()
        return True


    def get_analytics(self, url_id: int) -> Optional[list[Click]]:
        mapping = self.get_by_id(url_id)
        if mapping is None:
            return None
        return self.db.query(Click).filter(Click.url_mapping_id == url_id).order_by(Click.clicked_at.desc()).all()


    def get_by_short_code(self, short_code: str) -> str:
        return self.db.query(URLMapping).filter(URLMapping.short_code == short_code).first()