from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from myapp.models.url_mapping import Click, URLMapping
from myapp.models.user_model import Users
from myapp.schemas.url_mapping import URLMappingCreate


class URLRepository:
    def __init__(self, db: Session):
        self.db = db


    # Insert followed by read approach because assuming 90% requests contain new urls and 10% existing ones
    def create(self, original_url: str, user_id:int, url_id: int, short_code: str) -> URLMapping:
        mapping = URLMapping(
            url_id=url_id,
            user_id=user_id,
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
            raise e
        except Exception as e:
            # Handles non-database exceptions (e.g: AttributeError, TypeError)
            self.db.rollback()
            print(f"Unexpected application error: {e}")
            raise e


    def get_url_by_user_and_original_url(self, user_id: int, original_url: str):
        return self.db.query(URLMapping).filter(
                (URLMapping.user_id == user_id) &
                (URLMapping.original_url == original_url)
            ).first()


    def list_all(self, user: Users) -> list[URLMapping]:
        return self.db.query(URLMapping).filter(URLMapping.user_id == user.id).order_by(URLMapping.url_id.desc()).all()


    def get_by_id(self, url_id: int, user: Users) -> Optional[URLMapping]:
        return self.db.query(URLMapping).filter(URLMapping.url_id == url_id, URLMapping.user_id == user.id).first()

    
    def activate(self, url_id: int, user: Users) -> int:
        count = self.db.query(URLMapping).filter(
                (URLMapping.url_id == url_id) &
                (URLMapping.user_id == user.id)
            ).update({"is_active": True})

        self.db.commit()

        return count
        

    def deactivate(self, url_id: int, user: Users) -> str:
        mapping =  self.db.query(URLMapping).filter(
                (URLMapping.url_id == url_id) &
                (URLMapping.user_id == user.id)
            ).first()
        
        if not mapping:
            return None
        
        mapping.is_active = False
        self.db.commit()

        return mapping.short_code


    def get_analytics(self, url_id: int) -> Optional[list[Click]]:
        return self.db.query(Click).filter(Click.url_mapping_id == url_id).order_by(Click.clicked_at.desc()).all()


    def get_by_short_code(self, short_code: str) -> str:
        return self.db.query(URLMapping).filter(URLMapping.short_code == short_code).first()