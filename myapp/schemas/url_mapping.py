from datetime import datetime
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class URLMappingCreate(BaseModel):
    original_url: AnyHttpUrl = Field(..., description="The original long URL to shorten")


class URLMappingUpdate(BaseModel):
    original_url: AnyHttpUrl = Field(..., description="Updated original long URL")


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