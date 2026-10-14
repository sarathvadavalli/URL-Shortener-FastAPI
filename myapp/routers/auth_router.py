from dns import exception, resolver
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from myapp.core.config import settings
from myapp.core.csrf import csrf_token, require_csrf, rotate_csrf
from myapp.core.security import create_access_token, hash_password, verify_password
from myapp.core.time import utcnow
from myapp.database import get_db
from myapp.models.user_model import Users
from myapp.schemas.auth_user import MessageResponse, UserCreate, UserLogin

templates = Jinja2Templates(directory="myapp/templates")

router = APIRouter(
    prefix="/auth", tags=["Authentication"], dependencies=[Depends(require_csrf)]
)


def domain_has_mx_record(email: str) -> bool | None:
    domain = email.rsplit("@", 1)[-1]

    try:
        answers = resolver.resolve(domain, "MX", lifetime=3)
    except (
        resolver.NXDOMAIN,
        resolver.NoAnswer,
    ):
        return False
    except (
        resolver.NoNameservers,
        exception.Timeout,
        exception.DNSException,
    ):
        return None

    return any(str(answer.exchange).rstrip(".") for answer in answers)


@router.get("/login")
def login_page(request: Request):
    error = request.cookies.get("flash_error", "")
    response = templates.TemplateResponse(
        request,
        "login.html",
        context={"error": error, "csrf_token": csrf_token(request)},
    )
    if error != "":
        response.delete_cookie("flash_error")

    return response


@router.post(
    "/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    email = str(payload.email).strip().lower()

    try:
        TypeAdapter(EmailStr).validate_python(email)
    except ValidationError as e:
        reason = e.errors()[0]["msg"]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason
        )

    has_mx_record = domain_has_mx_record(email)
    if has_mx_record is False:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid email. Make sure it exists and is active.",
        )
    if has_mx_record is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify email domain right now. Please try again.",
        )

    try:
        existing_user = (
            db.query(Users)
            .filter((Users.user_name == username) | (Users.email == email))
            .first()
        )

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

        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username or email already exists.",
        ) from exc

    return {"message": "Account created successfully."}


@router.post("/login", response_model=MessageResponse)
def login_user(
    payload: UserLogin,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    identifier = payload.identifier.strip().lower()
    password = payload.password

    if not identifier or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Missing required fields",
        )

    if "@" in identifier:
        user = db.query(Users).filter(Users.email == identifier).first()
    else:
        user = db.query(Users).filter(Users.user_name == identifier).first()

    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user.last_login_at = utcnow()
    db.commit()

    rotate_csrf(request)
    token = create_access_token(user.user_name)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )

    return {"message": "Authentication successful"}


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response, request: Request):
    request.session.clear()
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )

    return {"message": "Logged out successfully"}
