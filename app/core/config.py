from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

APP_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, extra="ignore"
    )

    DB_DRIVER: str = "postgresql+asyncpg"
    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=5433, ge=1, le=65535)
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "retry_scheduler"

    MAX_ATTEMPTS: int = Field(default=5, ge=1)
    RETRY_BASE_DELAY_SECONDS: float = Field(default=1.0, gt=0)
    RETRY_MAX_DELAY_SECONDS: float = Field(default=60.0, gt=0)

    WORKER_CONCURRENCY: int = Field(default=4, ge=0)
    POLL_INTERVAL_SECONDS: float = Field(default=1.0, gt=0)
    LEASE_SECONDS: float = Field(default=30.0, gt=0)
    DELIVERY_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)

    SIMULATED_FAILURE_RATE: float = Field(default=0.3, ge=0, le=1)
    SIMULATED_MAX_LATENCY_SECONDS: float = Field(default=0.5, ge=0)
    SIMULATED_SEED: int | None = None

    @model_validator(mode="after")
    def lease_outlives_delivery(self) -> Self:
        if self.LEASE_SECONDS <= self.DELIVERY_TIMEOUT_SECONDS:
            raise ValueError(
                "LEASE_SECONDS must be greater than DELIVERY_TIMEOUT_SECONDS"
            )
        return self

    @property
    def DATABASE_URL(self) -> URL:
        return URL.create(
            self.DB_DRIVER,
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )


settings = Settings()
