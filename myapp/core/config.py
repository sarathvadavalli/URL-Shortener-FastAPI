from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "URL SHORTENER"
    DATABASE_URL: str

    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY")
    if not jwt_secret_key:
        raise RuntimeError("CRITICAL: JWT_SECRET_KEY environment variable is not set!")

    session_secret_key: str = os.getenv("SESSION_SECRET_KEY")
    if not session_secret_key:
        raise RuntimeError("CRITICAL: SESSION_SECRET_KEY environment variable is not set!")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()