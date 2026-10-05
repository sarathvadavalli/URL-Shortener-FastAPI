from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import ValidationError
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from starlette.concurrency import run_in_threadpool

from myapp.database import get_db
from myapp.services.url_service import URLService
from myapp.schemas.url_mapping import URLMappingCreate
from myapp.models.url_mapping import URLMapping, Click
from myapp.tasks import record_click

router = APIRouter()

templates = Jinja2Templates(directory="myapp/templates")


def render_template(name: str, context: dict) -> HTMLResponse:
    tpl = templates.env.get_template(name)
    return HTMLResponse(tpl.render(**context))


@router.get("/", include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)):
    total_urls = db.query(URLMapping).count()
    total_clicks = db.query(Click).count()
    service = URLService(db)
    recent = service.list_urls()[:10]
    return render_template("index.html", {"request": request, "total_urls": total_urls, "total_clicks": total_clicks, "recent": recent})


@router.get("/urls", include_in_schema=False)
def list_urls(request: Request, db: Session = Depends(get_db)):
    service = URLService(db)
    urls = service.list_urls()
    return render_template("urls.html", {"request": request, "urls": urls})


@router.get("/urls/create", include_in_schema=False)
def create_form(request: Request):
    short_code = request.session.pop("created_short_code", None)
    return render_template("url_form.html", {"request": request, "action": "create", "short_code": short_code})


@router.post("/urls/create", include_in_schema=False)
def create_url(request: Request, original_url: str = Form(...), db: Session = Depends(get_db)):
    form_context = {"request": request, "action": "create", "original_url": original_url}

    try:
        payload = URLMappingCreate(original_url=original_url)
    except ValidationError as e:
        messages = [err.get("msg", "") for err in e.errors() if err.get("msg")]
        error = "; ".join(messages) if messages else str(e)
        return render_template("url_form.html", {**form_context, "error": error})

    try:
        service = URLService(db)
        mapping = service.create_url(payload)
        if mapping is None:
            return render_template(
                "url_form.html",
                {**form_context, "error": "Failed to create short URL. Please try again."},
            )

        # Storing the short code in session storage temporarily and popping out in the GET request
        # Ensures that the shortcode is served only once as a flow: POST → store → redirect → GET → remove
        request.session["created_short_code"] = mapping.short_code
        return RedirectResponse(
            url="/urls/create",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        return render_template("url_form.html", {**form_context, "error": str(e)})


@router.post("/urls/{id}/delete", include_in_schema=False)
def delete_url(id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    service.delete_url(id)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/urls/{id}", include_in_schema=False)
def url_detail(request: Request, id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    mapping = service.get_url(id)
    if mapping is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)
    analytics = service.get_analytics(id) or []
    return render_template("url_detail.html", {"request": request, "url": mapping, "analytics": analytics})


@router.get("/{short_code}")
async def redirect(short_code: str, request: Request, db: Session = Depends(get_db)):
    url_service = URLService(db)

    # Redis → DB fallback
    data = await run_in_threadpool(
        url_service.get_original_by_short_code,
        short_code,
    )

    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Short code not found",
        )

    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    clicked_at = datetime.now(timezone.utc)

    # Send analytics event to Celery
    record_click.delay(
        data["url_mapping_id"],
        ip_address,
        user_agent,
        clicked_at,
    )

    # Redirects to the original URL
    return RedirectResponse(
        url=data["original_url"],
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.get("/urls/{id}/analytics/view", include_in_schema=False)
def view_analytics(request: Request, id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    analytics = service.get_analytics(id)
    if analytics is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)
    return render_template("analytics.html", {"request": request, "analytics": analytics})
