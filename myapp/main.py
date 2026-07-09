from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from myapp.database import SessionLocal, init_db
from myapp.models.url_mapping import URLMapping, Click
from myapp.routers.url_router import router as api_router
from myapp.routers.ui_router import router as ui_router

app = FastAPI(title="FIRST PROJECT")

app.include_router(ui_router)
app.include_router(api_router)

# serve static files (css/js/images)
app.mount("/static", StaticFiles(directory="myapp/static"), name="static")


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


@app.get("/healthz")
async def read_root():
    return {"message": "URL Shortener API is running"}