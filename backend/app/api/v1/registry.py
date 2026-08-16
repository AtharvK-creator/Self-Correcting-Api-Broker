"""
API Registry endpoints — FEAT-003.

GET  /api/v1/apis
POST /api/v1/apis
GET  /api/v1/apis/{api_id}
PATCH /api/v1/apis/{api_id}
"""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.registry import Api, ApiEndpoint, ApiParameter, ApiVersion

router = APIRouter()
logger = structlog.get_logger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ApiCreate(BaseModel):
    name: str
    description: str | None = None
    base_url: str
    registered_host: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()


class ApiResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    base_url: str
    registered_host: str
    is_active: bool

    model_config = {"from_attributes": True}


class ApiPatch(BaseModel):
    description: str | None = None
    is_active: bool | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/apis", response_model=list[ApiResponse], summary="List registered APIs")
async def list_apis(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Api).where(Api.is_active == True).order_by(Api.name))
    return result.scalars().all()


@router.post("/apis", response_model=ApiResponse, status_code=status.HTTP_201_CREATED, summary="Register a new API")
async def create_api(payload: ApiCreate, db: AsyncSession = Depends(get_db)):
    # Check for duplicate name
    existing = await db.execute(select(Api).where(Api.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"API with name '{payload.name}' already exists")

    api = Api(**payload.model_dump())
    db.add(api)
    await db.flush()
    await db.refresh(api)
    logger.info("api_registered", api_id=str(api.id), name=api.name)
    return api


@router.get("/apis/{api_id}", response_model=ApiResponse, summary="Get API by ID")
async def get_api(api_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    api = await db.get(Api, api_id)
    if not api:
        raise HTTPException(status_code=404, detail="API not found")
    return api


@router.patch("/apis/{api_id}", response_model=ApiResponse, summary="Update API")
async def patch_api(api_id: uuid.UUID, payload: ApiPatch, db: AsyncSession = Depends(get_db)):
    api = await db.get(Api, api_id)
    if not api:
        raise HTTPException(status_code=404, detail="API not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(api, field, value)
    await db.flush()
    await db.refresh(api)
    return api
