"""
Import all ORM models so SQLAlchemy's metadata is populated.
This ensures Alembic and test fixtures can discover all tables.
"""

from app.models.users import User  # noqa: F401
from app.models.registry import Api, ApiEndpoint, ApiVersion, ApiParameter  # noqa: F401
from app.models.events import RequestEvent, FailureEvent  # noqa: F401
from app.models.graph import GraphNode, GraphEdge, EmbeddingRecord  # noqa: F401
from app.models.recovery import (  # noqa: F401
    RecoveryCase,
    CorrectionCandidate,
    RecoveryAttempt,
    Policy,
    ApprovalRequest,
    AuditEvent,
    ModelRun,
    EvaluationRun,
)
