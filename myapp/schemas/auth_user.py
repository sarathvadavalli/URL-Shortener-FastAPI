from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str = Field(..., min_length=3, max_length=16)
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Username must contain only ASCII characters.")

        if not value[0].isalnum() or not value[-1].isalnum():
            raise ValueError(
                "Username must start and end with a letter or digit."
            )

        if not all(c.isalnum() or c in "_-" for c in value):
            raise ValueError(
                "Username can contain only letters, digits, '_' and '-'."
            )

        if "__" in value or "--" in value or "_-" in value or "-_" in value:
            raise ValueError(
                "Username cannot contain consecutive '_' or '-'."
            )

        return value


class UserLogin(BaseModel):
    identifier: str = Field(..., min_length=1)
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class UserProfile(BaseModel):
    name: str
    email: str
    created_at: datetime
    last_login_at: datetime | None = None
