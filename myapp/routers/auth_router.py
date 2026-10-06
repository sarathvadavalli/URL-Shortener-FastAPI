from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from myapp.core.config import settings
from myapp.core.security import create_access_token, hash_password, verify_password
from myapp.database import get_db
from myapp.models.user_model import Users
from myapp.schemas.auth_user import MessageResponse, UserCreate, UserLogin

templates = Jinja2Templates(directory="myapp/templates")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
def login_page(request: Request):
    error = request.cookies.get("flash_error", "")
    response = templates.TemplateResponse(
        request, 
        "login.html", 
        context={"error": error}
    )
    if error != "":
        response.delete_cookie("flash_error")

    return response


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    email = str(payload.email).strip().lower()

    existing_user = db.query(Users).filter(
        (Users.user_name == username) |
        (Users.email == email)
    ).first()

    if existing_user:
        if existing_user.user_name == username:
            raise HTTPException(409, "Username already exists")

        if existing_user.email == email:
            raise HTTPException(409, "Email already exists")

    user = Users(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        user_name=username,
        email=email,
        password=hash_password(payload.password),
    )

    try:
        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This username or email already exists.",
        ) from exc

    return {"message": "Account created successfully."}


@router.post("/login", response_model=MessageResponse)
def login_user(
    payload: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
):
    identifier = payload.identifier.strip().lower()

    if "@" in identifier:
        user = db.query(Users).filter(Users.email == identifier).first()
    else:
        user = db.query(Users).filter(Users.user_name == identifier).first()

    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or username or password.",
        )

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token(user.user_name)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60,
    )

    return {"message": "Authentication successful"}


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response):
    print("Logging out")
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return {"message": "Logged out successfully"}
