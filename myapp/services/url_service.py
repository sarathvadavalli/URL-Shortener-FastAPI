import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from myapp.models.url_mapping import Click, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate, URLMappingUpdate
from myapp.repos.url_repository import URLRepository


class URLService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = URLRepository(db)

    def create_url(self, payload: URLMappingCreate) -> Optional[URLMapping]:
        return self.repository.create(payload)

    def list_urls(self) -> list[URLMapping]:
        return self.repository.list_all()

    def get_url(self, url_id: int) -> Optional[URLMapping]:
        return self.repository.get_by_id(url_id)

    def update_url(self, url_id: int, payload: URLMappingUpdate) -> Optional[URLMapping]:
        return self.repository.update(url_id, payload)

    def delete_url(self, url_id: int) -> bool:
        return self.repository.delete(url_id)

    def get_analytics(self, url_id: int) -> Optional[list[Click]]:
        return self.repository.get_analytics(url_id)

    def get_original_by_code(self, short_code: str, user_agent: Optional[str], ip_address: Optional[str]) -> Optional[str]:
        original_url = self.repository.get_by_short_code(short_code, user_agent=user_agent, ip_address=ip_address)
        if original_url is None:
            return None

        return original_url