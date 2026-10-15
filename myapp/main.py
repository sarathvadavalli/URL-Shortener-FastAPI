from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from myapp.core.config import settings
from myapp.database import SessionLocal, init_db
from myapp.models.url_mapping import URLMapping
from myapp.models.user_model import Users
from myapp.routers.auth_router import router as auth_router
from myapp.routers.ui_router import router as ui_router


def seed_url_mappings():
    with SessionLocal() as db:
        if db.get(Users, 0) is None:
            connection = db.connection()
            original_sql_mode = None
            if connection.dialect.name in {"mysql", "mariadb"}:
                original_sql_mode = connection.execute(text("SELECT @@SESSION.sql_mode")).scalar_one()
                modes = [mode for mode in original_sql_mode.split(",") if mode]
                if "NO_AUTO_VALUE_ON_ZERO" not in modes:
                    modes.append("NO_AUTO_VALUE_ON_ZERO")
                connection.execute(text("SET SESSION sql_mode = :mode"), {"mode": ",".join(modes)})
            try:
                db.add(Users(
                    id=0,
                    first_name="Anonymous",
                    last_name="User",
                    user_name="anonymous",
                    email="anonymous@example.com",
                    password="!"  # The anonymous system user cannot log in.
                ))
                
                db.flush()
            finally:
                if original_sql_mode is not None:
                    connection.execute(text("SET SESSION sql_mode = :mode"), {"mode": original_sql_mode})

        if db.query(URLMapping).count() == 0:
            for url, code in [
                ("https://fastapi.tiangolo.com/", "fastapi"),
                ("https://docs.python.org/3/", "python"),
            ]:
                db.add(URLMapping(user_id=0, original_url=url, short_code=code))
        db.commit()


@asynccontextmanager
async def lifespan(app):
    init_db()
    seed_url_mappings()
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    https_only=True,
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
