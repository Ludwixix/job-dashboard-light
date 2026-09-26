"""
Application configuration and environment settings for Job Dashboard Light.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    ENVIRONMENT: str = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )
    PORT: int = Field(default_factory=lambda: int(os.getenv("PORT", "8080")))
    HOST: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))

    DATA_DIR: Path = Field(
        default_factory=lambda: Path(
            os.getenv(
                "JOB_DASHBOARD_DATA_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "data"),
            )
        )
    )
    GCS_DATA_BUCKET: Optional[str] = Field(
        default_factory=lambda: os.getenv(
            "JOB_DASHBOARD_GCS_DATA_BUCKET", "acaa-agent-job-dashboard-light-data"
        )
    )

    OPENROUTER_API_KEY: str = Field(
        default_factory=lambda: os.getenv("JOB_DASHBOARD_OPENROUTER_API_KEY", "")
    )
    DEFAULT_MODEL: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "deepseek/deepseek-chat")
    )

    JWT_SECRET_KEY: str = Field(
        default_factory=lambda: os.getenv(
            "JWT_SECRET_KEY", "dev-secret-key-change-in-production-12345"
        )
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = 7
    GOOGLE_CLIENT_ID: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "")
    )

    APIFY_API_TOKEN: Optional[str] = Field(
        default_factory=lambda: os.getenv("APIFY_API_TOKEN")
    )
    ADZUNA_APP_ID: Optional[str] = Field(
        default_factory=lambda: os.getenv("ADZUNA_APP_ID")
    )
    ADZUNA_APP_KEY: Optional[str] = Field(
        default_factory=lambda: os.getenv("ADZUNA_APP_KEY")
    )


settings = Settings()
