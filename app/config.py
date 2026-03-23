import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Distributed Job Processing System"
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    postgres_user: str = os.getenv("POSTGRES_USER", "appuser")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "apppassword")
    postgres_db: str = os.getenv("POSTGRES_DB", "jobs_db")
    postgres_host: str = os.getenv("POSTGRES_HOST", "db")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Redis / Celery
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    celery_broker_url: str | None = os.getenv("CELERY_BROKER_URL")
    celery_result_backend: str | None = os.getenv("CELERY_RESULT_BACKEND")

    # Auth
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "super-secret-dev-key")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )

    # Rate limiting
    rate_limit_jobs_per_minute: int = int(
        os.getenv("RATE_LIMIT_JOBS_PER_MINUTE", "10")
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()

