from typing import List
from urllib import request

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from myapp.database import get_db
from myapp.schemas.url_mapping import (
    URLMappingCreate,
    URLMappingResponse,
    ClickResponse,
)
from myapp.services.url_service import URLService

router = APIRouter()


@router.post("/shorten", response_model=URLMappingResponse, status_code=status.HTTP_201_CREATED)
def create_short_url(payload: URLMappingCreate, db: Session = Depends(get_db)):
    """Create a short URL. Delegates to service layer."""
    url_service = URLService(db)
    result = url_service.create_url(payload)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to create URL")
    
    return result


@router.get("/shorten", response_model=List[URLMappingResponse])
def list_urls(db: Session = Depends(get_db)):
    """List all URL mappings."""
    url_service = URLService(db)
    return url_service.list_urls()


@router.get("/shorten/{id}", response_model=URLMappingResponse)
def get_url(id: int, db: Session = Depends(get_db)):
    """Get one URL mapping by id."""
    url_service = URLService(db)
    result = url_service.get_url(id)
    if result is None:
        raise HTTPException(status_code=404, detail="URL mapping not found")
    
    return result


@router.delete("/shorten/{id}", status_code=status.HTTP_200_OK)
def delete_url(id: int, db: Session = Depends(get_db)):
    """Delete a URL mapping."""
    url_service = URLService(db)
    success = url_service.delete_url(id)
    if not success:
        raise HTTPException(status_code=404, detail="URL mapping not found")

    return {"message": "The URL mapping has been deleted successfully."}


@router.get("/shorten/{id}/analytics", response_model=List[ClickResponse])
def url_analytics(id: int, db: Session = Depends(get_db)):
    """Return analytics (clicks) for one URL mapping."""
    url_service = URLService(db)
    data = url_service.get_analytics(id)
    if data is None:
        raise HTTPException(status_code=404, detail="URL mapping not found")
    
    return data


@router.get("/{short_code}")
async def redirect(short_code: str, request: Request, db: Session = Depends(get_db)):
    """Redirect by short code to the original URL."""
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    url_service = URLService(db)
    original = await run_in_threadpool(
        url_service.get_original_by_code,
        short_code,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    if original is None:
        raise HTTPException(status_code=404, detail="Short code not found")

    return RedirectResponse(url=original, status_code=status.HTTP_307_TEMPORARY_REDIRECT)