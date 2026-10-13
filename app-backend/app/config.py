from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEVELOPMENT_JWT_SECRET = "development-only-secret-change-me-at-least-32-chars"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./sobracero.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = _DEVELOPMENT_JWT_SECRET
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=30, gt=0)
    refresh_cookie_name: str = "sc_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_path: str = "/api/v1/auth"
    cors_origins: str = "http://localhost:3000"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "lots"
    minio_public_url: str = "http://localhost:9000"
    minio_secure: bool = False
    minio_region: str = "us-east-1"

    llm_provider: str = "mock"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ai_model_fast: str = "claude-haiku-5-5"
    ai_model_smart: str = "claude-sonnet-5-5"
    ai_max_tokens: int = Field(default=512, gt=0, le=2048)
    ai_timeout_seconds: float = Field(default=20, gt=0, le=120)
    ai_daily_quota: int = Field(default=25, gt=0)
    ai_cache_ttl_seconds: int = Field(default=900, gt=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> Self:
        if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
            raise ValueError("SameSite=None refresh cookies must be secure")
        if self.app_environment == "production":
            if self.jwt_secret == _DEVELOPMENT_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("Production requires a JWT_SECRET of at least 32 characters")
            if not self.refresh_cookie_secure:
                raise ValueError("Production refresh cookies must be secure")
            if self.llm_provider == "mock":
                raise ValueError("Production requires a configured AI provider")
            if self.llm_provider == "anthropic" and not self.anthropic_api_key:
                raise ValueError("Anthropic requires ANTHROPIC_API_KEY")
            if self.llm_provider == "openai" and not (self.llm_api_key or self.openai_api_key):
                raise ValueError("OpenAI requires an API key")
        return self


settings = Settings()
