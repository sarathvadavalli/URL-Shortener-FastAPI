from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from myapp.core.config import settings
from myapp.database import SessionLocal, engine, init_db
from myapp.models.url_mapping import URLMapping
from myapp.routers.auth_router import router as auth_router
from myapp.routers.ui_router import router as ui_router
from myapp.services.url_service import url_digest


def seed_url_mappings():
    with SessionLocal() as db:
        if db.query(URLMapping).count() == 0:
            for url, code in [
                ("https://fastapi.tiangolo.com/", "fastapi"),
                ("https://docs.python.org/3/", "python"),
            ]:
                try:
                    with db.begin_nested():
                        db.add(
                            URLMapping(
                                user_id=None,
                                owner_key="seed",
                                url_hash=url_digest(url),
                                original_url=url,
                                short_code=code,
                            )
                        )
                        db.flush()
                except IntegrityError:
                    # Another worker may have seeded this same row concurrently.
                    existing = (
                        db.query(URLMapping)
                        .filter_by(owner_key="seed", url_hash=url_digest(url))
                        .with_for_update()
                        .first()
                    )
                    if existing is None:
                        raise
            db.commit()


@asynccontextmanager
async def lifespan(app):
    # Detect old schemas before create_all can add partial new tables.
    inspector = inspect(engine)
    if inspector.has_table("url_mappings"):
        names = {item["name"] for item in inspector.get_columns("url_mappings")}
        constraints = {
            item["name"] for item in inspector.get_unique_constraints("url_mappings")
        }
        if (
            not {"owner_key", "url_hash"} <= names
            or "uq_url_owner_hash" not in constraints
        ):
            raise RuntimeError(
                "Existing database needs migration: run alembic upgrade head"
            )
    init_db()
    columns = {item["name"] for item in inspect(engine).get_columns("url_mappings")}
    if not {"owner_key", "url_hash"} <= columns:
        raise RuntimeError(
            "Existing database needs migration: run alembic upgrade head"
        )
    seed_url_mappings()
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=settings.cookie_secure,
    same_site="lax",
)
app.include_router(ui_router)
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory="myapp/static"), name="static")


@app.middleware("http")
async def prevent_page_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/urls", "/auth")) or request.url.path == "/home":
        # Forms contain session-specific CSRF tokens as well as private content.
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if (
        exc.status_code == status.HTTP_401_UNAUTHORIZED
        and "text/html" in request.headers.get("accept", "")
    ):
        response = RedirectResponse("/auth/login", status_code=303)
        response.delete_cookie(
            "access_token", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
        response.set_cookie(
            "flash_error",
            "Your session has expired. Please login again",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    return RedirectResponse("/urls/create", status_code=302)
