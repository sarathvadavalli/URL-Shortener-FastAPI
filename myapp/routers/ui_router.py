from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from myapp.database import get_db
from myapp.services.url_service import URLService
from myapp.schemas.url_mapping import URLMappingCreate, URLMappingUpdate
from myapp.models.url_mapping import URLMapping, Click

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
    return render_template("url_form.html", {"request": request, "action": "create"})


@router.post("/urls/create", include_in_schema=False)
def create_url(request: Request, original_url: str = Form(...), db: Session = Depends(get_db)):
    try:
        payload = URLMappingCreate(original_url=original_url)
    except Exception as e:
        return render_template("url_form.html", {"request": request, "action": "create", "error": str(e)})

    service = URLService(db)
    service.create_url(payload)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/urls/{id}", include_in_schema=False)
def url_detail(request: Request, id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    mapping = service.get_url(id)
    if mapping is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)
    analytics = service.get_analytics(id) or []
    return render_template("url_detail.html", {"request": request, "url": mapping, "analytics": analytics})


@router.get("/urls/{id}/edit", include_in_schema=False)
def edit_form(request: Request, id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    mapping = service.get_url(id)
    if mapping is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)
    return render_template("url_form.html", {"request": request, "action": "edit", "url": mapping})


@router.post("/urls/{id}/edit", include_in_schema=False)
def edit_url(request: Request, id: int, original_url: str = Form(...), db: Session = Depends(get_db)):
    try:
        payload = URLMappingUpdate(original_url=original_url)
    except Exception as e:
        service = URLService(db)
        mapping = service.get_url(id)
        return render_template("url_form.html", {"request": request, "action": "edit", "url": mapping, "error": str(e)})

    service = URLService(db)
    service.update_url(id, payload)
    return RedirectResponse(url=f"/urls/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/urls/{id}/delete", include_in_schema=False)
def delete_url(id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    service.delete_url(id)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/urls/{id}/analytics/view", include_in_schema=False)
def view_analytics(request: Request, id: int, db: Session = Depends(get_db)):
    service = URLService(db)
    analytics = service.get_analytics(id)
    if analytics is None:
        return RedirectResponse(url="/urls", status_code=status.HTTP_303_SEE_OTHER)
    return render_template("analytics.html", {"request": request, "analytics": analytics})
