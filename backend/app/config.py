"""
Self-Correcting API Broker — application configuration.

All settings are loaded from environment variables (with .env file support).
Secrets are never hardcoded.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "testing", "production"] = "development"
    secret_key: str = Field(min_length=32)
    log_level: str = "INFO"

    # Database
    database_url: str
    database_url_sync: str
    test_database_url: str = ""

    # LLM providers — all optional; broker degrades gracefully without them
    llm_provider: Literal["gemini", "groq", "mock"] = "mock"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    llm_max_tokens: int = 2048
    llm_timeout_seconds: int = 30
    llm_cost_budget_usd_per_request: float = 0.05

    # Recovery engine thresholds (configurable experimental parameters)
    confidence_threshold: float = 0.65
    min_evidence_count: int = 2
    ranking_weight_graph_similarity: float = 0.30
    ranking_weight_historical_success: float = 0.25
    ranking_weight_schema_compatibility: float = 0.20
    ranking_weight_failure_match: float = 0.15
    ranking_weight_provenance_quality: float = 0.10

    # Upstream execution
    upstream_timeout_seconds: int = 30
    upstream_max_redirects: int = 3
    upstream_verify_tls: bool = True
    upstream_allowed_hosts: str = ""  # comma-separated; empty = registry only

    # CORS
    cors_allow_origins: str = "http://localhost:3000"

    # JWT
    jwt_access_token_expire_minutes: int = 60

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_not_be_placeholder(cls, v: str) -> str:
        forbidden = {"change-me", "changeme", "secret", "placeholder"}
        if any(f in v.lower() for f in forbidden) and len(v) < 32:
            raise ValueError(
                "SECRET_KEY appears to be a placeholder. "
                "Set a real secret (≥32 chars) in your .env file."
            )
        return v

    @property
    def ranking_weights(self) -> dict[str, float]:
        return {
            "graph_similarity": self.ranking_weight_graph_similarity,
            "historical_success": self.ranking_weight_historical_success,
            "schema_compatibility": self.ranking_weight_schema_compatibility,
            "failure_match": self.ranking_weight_failure_match,
            "provenance_quality": self.ranking_weight_provenance_quality,
        }

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def allowed_upstream_hosts(self) -> list[str]:
        return [h.strip() for h in self.upstream_allowed_hosts.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
