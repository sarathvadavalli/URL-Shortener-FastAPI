from pydantic import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "URL SHORTENER"
    DATABASE_URL: str
    SECRET_KEY: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
