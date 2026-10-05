import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from myapp.database import get_db, redis_client
from myapp.models.url_mapping import Click, URLMapping
from myapp.schemas.url_mapping import URLMappingCreate
from myapp.repos.url_repository import URLRepository
from myapp.services.id_generator import IDGenerator


class URLService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = URLRepository(db)


    def create_url(self, payload: URLMappingCreate):
        # Generate a unique ID through an application level ID-generator
        id_generator = IDGenerator()
        url_id = id_generator.next_id()

        # Generate short code using base-62 encoding technique
        short_code = self._generate_short_code(url_id)

        return self.repository.create(payload, url_id, short_code)


    # Using Base-62 encoding of url_id for shortcode generation
    # Because it is space efficient and also guarantees uniqueness
    def _generate_short_code(self, url_id: int) -> str:
        value = url_id
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


    def list_urls(self) -> list[URLMapping]:
        return self.repository.list_all()

    def get_url(self, url_id: int):
        return self.repository.get_by_id(url_id)

    def delete_url(self, url_id: int) -> bool:
        return self.repository.delete(url_id)

    def get_analytics(self, url_id: int) -> Optional[list[Click]]:
        return self.repository.get_analytics(url_id)


    def get_original_by_short_code(self, short_code: str):
        cache_key = f"url:{short_code}"

        # Check Redis if shortcode already exists
        cached = redis_client.get(cache_key)

        if cached:
            print("Served from cache..")
            return json.loads(cached)

        # If cache miss → fetch from DB
        mapping = self.repository.get_by_short_code(short_code)

        if mapping is None:
            return None

        data = {
            "url_mapping_id": mapping.url_id,
            "original_url": str(mapping.original_url),
        }

        # 3. Store in Redis
        redis_client.set(
            cache_key,
            json.dumps(data),
            ex=3600,
        )

        return data