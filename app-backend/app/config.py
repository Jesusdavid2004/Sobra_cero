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

    llm_provider: str = "mock"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None

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
        return self


settings = Settings()
