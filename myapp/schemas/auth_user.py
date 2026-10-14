from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    username: str = Field(..., min_length=3, max_length=16)
    email: str
    password: str = Field(..., min_length=6)

    @model_validator(mode="before")
    @classmethod
    def check_missing_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        required_fields = cls.model_fields.keys()

        missing_fields = [
            field
            for field in required_fields
            if field not in data
            or data[field] is None
            or (isinstance(data[field], str) and not data[field].strip())
        ]

        if missing_fields:
            raise PydanticCustomError(
                "missing_fields_error",
                f"The following required fields are missing: {missing_fields}",
            )

        return data

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Username must contain only ASCII characters")

        if not value[0].isalnum() or not value[-1].isalnum():
            raise ValueError("Username must start and end with a letter or digit")

        if not all(c.isalnum() or c in "_-" for c in value):
            raise ValueError("Username can contain only letters, digits, '_' and '-'")

        if "__" in value or "--" in value or "_-" in value or "-_" in value:
            raise ValueError("Username cannot contain consecutive '_' or '-'")

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
