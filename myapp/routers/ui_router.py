import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from myapp.core.csrf import csrf_token, require_csrf
from myapp.core.security import get_current_user
from myapp.database import get_db
from myapp.models.user_model import Users
from myapp.schemas.url_mapping import URLMappingCreate
from myapp.services.url_service import URLService
from myapp.tasks import record_click

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_csrf)])

templates = Jinja2Templates(directory="myapp/templates")
templates.env.autoescape = select_autoescape(["html", "xml"])


def render_template(
    name: str,
    context: dict,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    context = {**context, "csrf_token": csrf_token(context["request"])}
    tpl = templates.env.get_template(name)
    return HTMLResponse(tpl.render(**context), status_code=status_code)


@router.get("/home", include_in_schema=False)
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)

    values = service.get_summary(user)
    total_urls = 0 if values[0] is None else values[0]
    total_clicks = 0 if values[1] is None else values[1]

    recent = service.list_urls(user)[:5]
    return render_template(
        "home.html",
        {
            "request": request,
            "is_authenticated": True,
            "total_urls": total_urls,
            "total_clicks": total_clicks,
            "recent": recent,
        },
    )


@router.get("/urls", include_in_schema=False)
def list_urls(
    request: Request,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)
    urls = service.list_urls(user)

    active_urls = [url for url in urls if url.is_active]
    inactive_urls = [url for url in urls if not url.is_active]

    return render_template(
        "urls.html",
        {
            "request": request,
            "is_authenticated": True,
            "active_urls": active_urls,
            "inactive_urls": inactive_urls,
            "active_count": len(active_urls),
            "inactive_count": len(inactive_urls),
        },
    )


def creation_owner(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if token:
        user = get_current_user(token, db)
        return user.id, f"u:{user.id}"
    guest = request.session.get("guest_id")
    if not guest:
        guest = str(uuid4())
        request.session["guest_id"] = guest
    return None, f"g:{guest}"


@router.get("/urls/create", include_in_schema=False)
def create_form(request: Request, db: Session = Depends(get_db)):
    user_id, _ = creation_owner(request, db)
    return render_template(
        "url_form.html",
        {
            "request": request,
            "is_authenticated": user_id is not None,
            "idempotency_key": str(uuid4()),
        },
    )


@router.post("/urls", include_in_schema=False)
def create_url(
    request: Request,
    original_url: str = Form(...),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id, owner_key = creation_owner(request, db)
    form_context = {
        "request": request,
        "original_url": original_url,
        "is_authenticated": user_id is not None,
        "idempotency_key": idempotency_key,
    }
    try:
        payload = URLMappingCreate(original_url=original_url)
        request_key = str(UUID(idempotency_key))
    except (ValidationError, ValueError) as exc:
        error = "Invalid URL or idempotency key"
        if isinstance(exc, ValidationError):
            error = "; ".join(item["msg"] for item in exc.errors())
        return render_template(
            "url_form.html",
            {
                **form_context,
                "error": error,
                "idempotency_key": str(uuid4()),
            },
            status_code=422,
        )
    try:
        mapping = URLService(db).create_url(payload, user_id, owner_key, request_key)
    except HTTPException as exc:
        return render_template(
            "url_form.html",
            {**form_context, "error": exc.detail},
            status_code=exc.status_code,
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("URL creation transaction failed")
        return render_template(
            "url_form.html",
            {
                **form_context,
                "error": "Unable to create short URL; please retry",
            },
            status_code=503,
        )
    # Creation and replay both return the original result with HTTP 200.
    # The fresh form key permits the next, independent operation.
    return render_template(
        "url_form.html",
        {
            **form_context,
            "original_url": mapping.original_url,
            "short_code": mapping.short_code,
            "idempotency_key": str(uuid4()),
        },
    )


@router.get("/urls/{id}", include_in_schema=False)
def url_detail(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)
    mapping = service.get_url(id, user)
    if mapping is None:
        raise HTTPException(status_code=404, detail="URL mapping not found")

    analytics = service.get_recent_analytics(id, user) or []

    message = request.session.pop("message", None)

    return render_template(
        "url_detail.html",
        {
            "request": request,
            "is_authenticated": True,
            "message": message,
            "url": mapping,
            "analytics": analytics,
        },
    )


@router.post("/urls/{id}/activate", include_in_schema=False)
def activate_url(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)
    activated = service.activate_url(id, user)
    if not activated:
        raise HTTPException(status_code=404, detail="Could not activate the URL")

    request.session["message"] = "activated"
    return RedirectResponse(url=f"/urls/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/urls/{id}/deactivate", include_in_schema=False)
def deactivate_url(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)
    deactivated = service.deactivate_url(id, user)
    if not deactivated:
        raise HTTPException(status_code=404, detail="Could not deactivate the URL")

    request.session["message"] = "deactivated"
    return RedirectResponse(url=f"/urls/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/urls/{id}/analytics/view", include_in_schema=False)
def view_analytics(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Users = Depends(get_current_user),
):
    service = URLService(db)
    analytics = service.get_analytics(id, user)
    if analytics is None:
        raise HTTPException(status_code=404, detail="Analytics not found")

    return render_template(
        "analytics.html",
        {"request": request, "is_authenticated": True, "analytics": analytics},
    )


@router.get("/{short_code}")
def redirect(
    request: Request,
    short_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    url_service = URLService(db)

    # FastAPI runs this synchronous route in its worker pool.
    try:
        data = url_service.get_original_by_short_code(short_code)
    finally:
        # Release the read transaction before the independent background write.
        db.rollback()

    if not data:
        raise HTTPException(
            status_code=404,
            detail="The page you are looking for doesnot exist",
        )

    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    clicked_at = datetime.now(UTC)

    background_tasks.add_task(
        record_click, data["url_mapping_id"], ip_address, user_agent, clicked_at
    )

    # Redirects to the original URL
    return RedirectResponse(
        url=data["original_url"],
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
