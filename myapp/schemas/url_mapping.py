from datetime import datetime
from typing import Optional
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator
from urllib.parse import urlparse

SHORTENER_DOMAIN = "localhost:8000"

class URLMappingCreate(BaseModel):
    original_url: AnyHttpUrl = Field(...,  min_length=10, max_length=2048)

    @field_validator("original_url")
    @classmethod
    def validate_scheme(cls, value):
        try:
            parsed = urlparse(str(value).rstrip('/'))
        except Exception:
            raise ValueError("Invalid URL structure")

        # 1. Require valid HTTP/HTTPS scheme
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("URL scheme must be http or https")

        # 2. Extract domain/host safely
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL must include a valid host domain")

        # 3. Prevent invalid domain names
        if ".." in hostname:
             raise ValueError("URL contains an invalid domain")

        # 4. Require a Top-Level Domain (e.g. .com, .org)
        if "." not in hostname:
            raise ValueError("URL must contain a valid top-level domain (e.g. .com)")

        # 5. Prevent self-referencing shortener domain
        if hostname == SHORTENER_DOMAIN:
            raise ValueError("Cannot shorten a URL from the shortener domain")

        return value


class URLMappingResponse(BaseModel):
    url_id: int
    original_url: AnyHttpUrl
    short_code: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClickCreate(BaseModel):
    user_agent: Optional[str] = Field(default=None, max_length=255)
    ip_address: Optional[str] = Field(default=None, max_length=45)


class ClickResponse(BaseModel):
    click_id: int
    url_mapping_id: int
    clicked_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)