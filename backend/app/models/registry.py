"""
SQLAlchemy ORM models — API registry.

Covers: apis, api_endpoints, api_versions, api_parameters.
Uses sa.JSON (not JSONB) for cross-dialect compatibility;
the migration uses JSONB for PostgreSQL specifically.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Api(Base):
    __tablename__ = "apis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # Registered host is verified against SSRF controls before upstream execution
    registered_host: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    endpoints: Mapped[list["ApiEndpoint"]] = relationship(back_populates="api", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Api id={self.id} name={self.name!r}>"


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apis.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # GET, POST, PUT, PATCH, DELETE
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # Whether this endpoint is idempotent (required for AUTO_ELIGIBLE auto-retry)
    is_idempotent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    api: Mapped["Api"] = relationship(back_populates="endpoints")
    versions: Mapped[list["ApiVersion"]] = relationship(back_populates="endpoint", cascade="all, delete-orphan")
    parameters: Mapped[list["ApiParameter"]] = relationship(back_populates="endpoint", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ApiEndpoint {self.method} {self.path}>"


class ApiVersion(Base):
    __tablename__ = "api_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_string: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_snapshot: Mapped[dict] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    endpoint: Mapped["ApiEndpoint"] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<ApiVersion {self.version_string}>"


class ApiParameter(Base):
    __tablename__ = "api_parameters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(32), nullable=False)  # query, header, path, body
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # Known aliases for this parameter (for deterministic rename recovery)
    known_aliases: Mapped[list] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version_introduced: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_deprecated: Mapped[str | None] = mapped_column(String(64), nullable=True)

    endpoint: Mapped["ApiEndpoint"] = relationship(back_populates="parameters")

    def __repr__(self) -> str:
        return f"<ApiParameter {self.name!r} in {self.location!r}>"
