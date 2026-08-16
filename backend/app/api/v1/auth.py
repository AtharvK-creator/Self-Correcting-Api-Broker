"""
Auth endpoints — FEAT-039.

POST /api/v1/auth/register
POST /api/v1/auth/token
GET  /api/v1/auth/me
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    TokenResponse,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.users import User

router = APIRouter(prefix="/auth")
logger = structlog.get_logger(__name__)


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "DEVELOPER"

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("username must be at least 3 characters")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("password must be at least 12 characters")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        allowed = {"DEVELOPER", "ADMIN", "REVIEWER", "READ_ONLY"}
        if v.upper() not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v.upper()


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check duplicate username
    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info("user_registered", user_id=str(user.id), username=user.username)
    return user


@router.post("/token", response_model=TokenResponse, summary="Obtain access token")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == form.username.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        # Generic error message — never reveal which field was wrong
        logger.warning("auth_login_failed", username=form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    from app.config import get_settings
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user.id), "username": user.username, "role": user.role}
    )
    logger.info("user_logged_in", user_id=str(user.id), username=user.username)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
