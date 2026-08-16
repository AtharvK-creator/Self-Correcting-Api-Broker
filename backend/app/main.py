"""
Self-Correcting API Broker — FastAPI application entry point.

Architecture invariants preserved:
- Deterministic recovery attempted before LLM
- LLM is candidate generator only, never execution authority
- Safety is fail-closed
- Maximum 2 upstream executions enforced in recovery state machine
"""

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.observability.logging import configure_logging
from app.auth.middleware import auth_middleware

# Import routers (registered as they are implemented)
from app.api.v1 import auth, health, registry, broker, recovery, memory, graph, analytics, evaluation, approvals, audit

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "broker_startup",
        env=settings.app_env,
        llm_provider=settings.llm_provider,
    )
    yield
    logger.info("broker_shutdown")


app = FastAPI(
    title="Self-Correcting API Broker",
    description=(
        "Reliability layer that recovers external API failures using "
        "contextual graph learning and bounded, auditable recovery."
    ),
    version="0.1.0",
    lifespan=lifespan,
    # Disable /docs in production as an extra precaution
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# ── Rate limiting + auth middleware ──────────────────────────────────────────
app.middleware("http")(auth_middleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ── Correlation ID middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    # Never expose raw stack traces to clients
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "correlation_id": getattr(request.state, "correlation_id", None)},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1", tags=["Auth"])
app.include_router(registry.router, prefix="/api/v1", tags=["Registry"])
app.include_router(broker.router, prefix="/api/v1", tags=["Broker"])
app.include_router(recovery.router, prefix="/api/v1", tags=["Recovery"])
app.include_router(memory.router, prefix="/api/v1", tags=["Recovery Memory"])
app.include_router(graph.router, prefix="/api/v1", tags=["Graph"])
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
app.include_router(evaluation.router, prefix="/api/v1", tags=["Evaluation"])
app.include_router(approvals.router, prefix="/api/v1", tags=["Approvals"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])
