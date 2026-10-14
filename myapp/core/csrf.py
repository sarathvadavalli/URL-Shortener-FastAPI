import hmac
import secrets

from fastapi import HTTPException, Request


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def rotate_csrf(request: Request):
    request.session["csrf_token"] = secrets.token_urlsafe(32)


async def require_csrf(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get("csrf_token")
    supplied = request.headers.get("x-csrf-token")
    if not supplied and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        supplied = (await request.form()).get("csrf_token")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or not hmac.compare_digest(expected.encode(), supplied.encode())
    ):
        raise HTTPException(403, "Invalid CSRF token; reload the form and try again")
        