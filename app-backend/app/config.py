from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = "sqlite:///./sobracero.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-secret"
    access_token_expire_minutes: int = 60
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


settings = Settings()
