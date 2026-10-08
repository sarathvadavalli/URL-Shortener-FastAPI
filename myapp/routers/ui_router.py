from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Form, Depends
from fastapi import HTTPException, status, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from myapp.core.security import get_current_user
from myapp.database import get_db, redis_client
from myapp.services.url_service import URLService
from myapp.schemas.url_mapping import URLMappingCreate
from myapp.models.url_mapping import URLMapping, Click
from myapp.models.user_model import Users
from myapp.tasks import record_click

router = APIRouter()

templates = Jinja2Templates(directory="myapp/templates")

def render_template(
    name: str,
    context: dict,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    tpl = templates.env.get_template(name)
    return HTMLResponse(tpl.render(**context), status_code=status_code)


@router.get("/home", include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db), user: Users=Depends(get_current_user)):
    total_urls = db.query(URLMapping).count()
    total_clicks = db.query(Click).count()
    service = URLService(db)
    recent = service.list_urls(user)[:10]
    return render_template("home.html", {"request": request, "is_authenticated": True,  "total_urls": total_urls, "total_clicks": total_clicks, "recent": recent})


@router.get("/urls", include_in_schema=False)
def list_urls(request: Request, db: Session = Depends(get_db), user: Users = Depends(get_current_user)):
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
        }
    )


@router.get("/urls/create", include_in_schema=False)
def create_form(request: Request, db: Session = Depends(get_db)):
    short_code = request.session.pop("created_short_code", None)
    token = request.cookies.get('access_token')

    user = None
    if token:
        try:
            user = get_current_user(token, db)
        except HTTPException:
            user = None

    return render_template("url_form.html", 
            {
                "request": request, 
                "action": "create", 
                "is_authenticated": user is not None,
                # "idempotency_key": str(uuid4()),
            }
        )


@router.post("/urls", include_in_schema=False)
def create_url(request: Request, original_url: str = Form(...), idempotency_key: str = Form(...), db: Session = Depends(get_db)):
    original_url = original_url.rstrip('/')
    form_context = {"request": request, "action": "create", "original_url": original_url}

    try:
        payload = URLMappingCreate(original_url=original_url)
        idempotency_key = str(UUID(idempotency_key))
    except ValidationError as e:
        messages = [err.get("msg", "") for err in e.errors() if err.get("msg")]
        error = "; ".join(messages) if messages else str(e)
        return render_template(
            "url_form.html",
            {**form_context, "error": error},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        # Get authenticated user ID if logged in else 0 for anonymous users
        token = request.cookies.get('access_token')
        user_id = 0
        if token:
            user = get_current_user(token, db)
            user_id = user.id

        idempotency_key = f"idempotency:url-create:{idempotency_key}"

        if redis_client.get(idempotency_key) == 'success':
            return RedirectResponse(
                url="/urls/create",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        service = URLService(db)
        mapping = service.create_url(
            payload=payload,
            user_id=user_id,
        )

        if mapping is None:
            return render_template(
                "url_form.html",
                {**form_context, "error": "Failed to create short URL. Please try again."},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        redis_client.set(idempotency_key, "success", ex=300)

        return render_template("url_form.html", 
            {
                "request": request, 
                "action": "create", 
                "original_url": original_url,
                "short_code": mapping.short_code,
                "is_authenticated": (user_id != 0),
            }
        )

    except Exception as e:
        print(e)
        return render_template(
            "url_form.html",
            {**form_context, "error": "Unable to create short code"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get("/urls/{id}", include_in_schema=False)
def url_detail(request: Request, id: int,
    db: Session = Depends(get_db), user: Users=Depends(get_current_user)
):
    service = URLService(db)
    mapping = service.get_url(id, user)
    if mapping is None:
        raise HTTPException(status_code=404, detail="URL mapping not found")

    analytics = service.get_analytics(id) or []

    message = request.session.pop('message', None)

    return render_template("url_detail.html", 
        {"request": request, "is_authenticated": True, "message": message,
        "url": mapping, "analytics": analytics})


@router.post("/urls/{id}/activate", include_in_schema=False)
def activate_url(request: Request, id: int, db: Session = Depends(get_db), user: Users=Depends(get_current_user)):
    service = URLService(db)
    activated = service.activate_url(id, user)
    if not activated:
        raise HTTPException(status_code=404, detail="Could not activate the URL")

    request.session['message'] = "activated"
    return RedirectResponse(url=f"/urls/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/urls/{id}/deactivate", include_in_schema=False)
def deactivate_url(request: Request, id: int, db: Session = Depends(get_db), user: Users=Depends(get_current_user)):
    service = URLService(db)
    deactivated = service.deactivate_url(id, user)
    if not deactivated:
        raise HTTPException(status_code=404, detail="Could not deactivate the URL")

    request.session['message'] = "deactivated"
    return RedirectResponse(url=f"/urls/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/urls/{id}/analytics/view", include_in_schema=False)
def view_analytics(request: Request, id: int, db: Session = Depends(get_db), user: Users=Depends(get_current_user)):
    service = URLService(db)
    analytics = service.get_analytics(id)
    if analytics is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)

    return render_template("analytics.html", {"request": request, "is_authenticated": True, "analytics": analytics})


@router.get("/{short_code}")
async def redirect(request: Request, short_code: str, 
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    url_service = URLService(db)

    # Calling the service using a worker thread to prevent blocking event loop
    data = await run_in_threadpool(
        url_service.get_original_by_short_code,
        short_code
    )

    if not data or data == "Not active":
        raise HTTPException(
            status_code=404,
            detail="The page you are looking for doesnot exist",
        )

    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    clicked_at = datetime.now(timezone.utc)

    # Send analytics event to Celery
    # record_click.delay(
    #     data["url_mapping_id"],
    #     ip_address,
    #     user_agent,
    #     clicked_at,
    # )

    # Send analytics event as background task to FastAPI
    background_tasks.add_task(
        record_click, 
        data["url_mapping_id"],
        ip_address,
        user_agent,
        clicked_at
    )

    # Redirects to the original URL
    return RedirectResponse(
        url=data["original_url"],
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )