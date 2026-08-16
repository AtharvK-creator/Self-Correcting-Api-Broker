"""
Database engine and session factory.

Uses async SQLAlchemy with asyncpg for the application and sync SQLAlchemy
for Alembic migrations.

The engine is lazily initialised so that importing this module does not
require database environment variables to be present (important for tests
and for Alembic offline mode).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""
    pass


@lru_cache(maxsize=1)
def _get_engine() -> AsyncEngine:
    """Build (and cache) the async engine from current settings."""
    from app.config import get_settings
    settings = get_settings()
    kwargs: dict = {
        "echo": settings.app_env == "development",
        "pool_pre_ping": True,
    }
    # SQLite (used in tests) doesn't support pool_size / max_overflow
    if not settings.database_url.startswith("sqlite"):
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_async_engine(settings.database_url, **kwargs)


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=_get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
