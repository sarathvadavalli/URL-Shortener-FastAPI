import base64, hashlib, hmac
import os, json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from myapp.core.config import settings as app_settings
from myapp.database import get_db
from myapp.models.user_model import Users


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
    )
    return (
        f"pbkdf2_sha256$100000$"
        f"{base64.b64encode(salt).decode()}$"
        f"{base64.b64encode(digest).decode()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected_digest = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(
            base64.b64encode(digest).decode(),
            expected_digest,
        )
    except (ValueError, TypeError):
        return False


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=app_settings.jwt_access_token_expire_minutes
    )
    header = {"alg": app_settings.jwt_algorithm, "typ": "JWT"}
    payload = {"sub": subject, "exp": int(expires_at.timestamp())}
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        app_settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        header = json.loads(_base64url_decode(encoded_header))
        if header.get("alg") != app_settings.jwt_algorithm:
            raise ValueError("Unsupported token algorithm.")

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            app_settings.jwt_secret_key.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(
            _base64url_encode(expected_signature),
            encoded_signature,
        ):
            raise ValueError("Invalid token signature.")

        payload = json.loads(_base64url_decode(encoded_payload))
        expires_at = payload.get("exp")
        now = int(datetime.now(timezone.utc).timestamp())
        if not isinstance(expires_at, int) or expires_at < now:
            raise ValueError("Token expired.")

        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid token.") from exc


def get_current_user(
    token: str | None = Cookie(default=None, alias="access_token"),
    db: Session = Depends(get_db),
) -> Users:
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    username = payload.get("sub")
    user = db.query(Users).filter(Users.user_name == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user