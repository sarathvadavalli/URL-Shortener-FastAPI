from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from myapp.core.config import settings
from myapp.database import SessionLocal, init_db
from myapp.models.url_mapping import URLMapping, Click
from myapp.routers.ui_router import router as ui_router
from myapp.routers.auth_router import router as auth_router

app = FastAPI(title="FIRST PROJECT")

session_secret = settings.session_secret_key
app.add_middleware(SessionMiddleware, secret_key=session_secret)

app.include_router(ui_router)
app.include_router(auth_router)

# serve static files (css/js/images)
app.mount("/static", StaticFiles(directory="myapp/static"), name="static")

PROTECTED_UI_ROUTES = {
    "/home",
    "/urls",
    "/urls/{id}",
    "/urls/{id}/analytics/view",
}

@app.middleware("http")
async def prevent_protected_page_caching(request: Request, call_next):
    response = await call_next(request)
    route = request.scope.get("route")
    if route is not None and route.path in PROTECTED_UI_ROUTES:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header:
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie(key="access_token")
            return response

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    return RedirectResponse(url="/urls/create", status_code=302)


@app.on_event("startup")
def startup_event():
    init_db()
    seed_url_mappings()


def seed_url_mappings():
    db = SessionLocal()
    try:
        if db.query(URLMapping).count() == 0:
            initial_url_mappings = [
                URLMapping(
                    original_url="https://fastapi.tiangolo.com/",
                    short_code="fastapi",
                ),
                URLMapping(
                    original_url="https://docs.python.org/3/",
                    short_code="python",
                ),
            ]
            db.add_all(initial_url_mappings)
            db.commit()
    finally:
        db.close()
