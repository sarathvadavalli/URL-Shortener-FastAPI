from typing import Optional

from sqlalchemy.orm import Session

from myapp.models.url_mapping import Click, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate, URLMappingUpdate


class URLRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: URLMappingCreate) -> URLMapping:
        short_code = self._generate_short_code()
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

    def _generate_short_code(self) -> str:
        while True:
            short_code = self._random_code(6)
            if self.get_by_short_code(short_code, None, None) is None:
                return short_code

    @staticmethod
    def _random_code(length: int) -> str:
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def _utcnow():
        from datetime import datetime

        return datetime.utcnow()
