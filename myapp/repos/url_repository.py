from typing import Optional

from sqlalchemy.orm import Session

from myapp.models.url_mapping import Click, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate, URLMappingUpdate


class URLRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: URLMappingCreate) -> URLMapping:
        last_mapping = self.db.query(URLMapping).order_by(URLMapping.url_id.desc()).first()
        next_id = (last_mapping.url_id if last_mapping is not None else 0) + 1
        short_code = self._generate_short_code(next_id)

        mapping = URLMapping(
            original_url=str(payload.original_url),
            short_code=short_code,
        )
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def list_all(self) -> list[URLMapping]:
        return self.db.query(URLMapping).order_by(URLMapping.url_id.desc()).all()

    def get_by_id(self, url_id: int) -> Optional[URLMapping]:
        return self.db.query(URLMapping).filter(URLMapping.url_id == url_id).first()

    def replace(self, url_id: int, payload: URLMappingUpdate) -> Optional[URLMapping]:
        mapping = self.get_by_id(url_id)
        if mapping is None:
            return None

        mapping.original_url = str(payload.original_url)
        mapping.updated_at = self._utcnow()
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def update(self, url_id: int, payload: URLMappingUpdate) -> Optional[URLMapping]:
        mapping = self.get_by_id(url_id)
        if mapping is None:
            return None

        mapping.original_url = str(payload.original_url)
        mapping.updated_at = self._utcnow()
        self.db.commit()
        self.db.refresh(mapping)
        return mapping

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

    def get_by_short_code(self, short_code: str, user_agent: Optional[str], ip_address: Optional[str]) -> str:
        mapping = self.db.query(URLMapping).filter(URLMapping.short_code == short_code).first()
        if mapping is None:
            return None
        
        click = Click(url_mapping_id=mapping.url_id,
                      user_agent=user_agent,
                      ip_address=ip_address
                      )
        self.db.add(click)
        self.db.commit()
        self.db.refresh(click)
        return str(mapping.original_url)

    
    def _generate_short_code(self, url_id: int) -> str:
        return self._encode_base62(url_id)

    @staticmethod
    def _encode_base62(value: int) -> str:
        if value < 0:
            raise ValueError("value must be non-negative")

        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if value == 0:
            return "0"

        encoded = []
        while value > 0:
            value, remainder = divmod(value, 62)
            encoded.append(alphabet[remainder])

        return "".join(reversed(encoded))

    @staticmethod
    def _utcnow():
        from datetime import datetime

        return datetime.utcnow()
