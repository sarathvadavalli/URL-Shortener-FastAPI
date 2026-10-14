from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "URL Shortener"
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/1"
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=60, ge=1)
    jwt_secret_key: str = Field(min_length=1)
    session_secret_key: str = Field(min_length=1)
    cookie_secure: bool = True
    shortener_domain: str = "url-shortener-fastapi-rato.onrender.com"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
