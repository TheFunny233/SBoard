from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "sboard.db"
DEFAULT_ADMIN_TOKEN = "sboard-development-token"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    admin_token: str
    database_url: str
    heartbeat_interval_seconds: int
    offline_threshold_seconds: int

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"

    def validate(self) -> None:
        if self.heartbeat_interval_seconds < 10:
            raise RuntimeError("SBOARD_HEARTBEAT_INTERVAL_SECONDS must be at least 10")
        if self.offline_threshold_seconds < self.heartbeat_interval_seconds * 2:
            raise RuntimeError("SBOARD_OFFLINE_THRESHOLD_SECONDS must be at least two heartbeats")
        if self.production and (
            self.admin_token == DEFAULT_ADMIN_TOKEN or len(self.admin_token) < 32
        ):
            raise RuntimeError("Production requires SBOARD_ADMIN_TOKEN with at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    default_url = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    return Settings(
        environment=os.getenv("SBOARD_ENV", "development"),
        admin_token=os.getenv("SBOARD_ADMIN_TOKEN", DEFAULT_ADMIN_TOKEN),
        database_url=os.getenv("SBOARD_DATABASE_URL", default_url),
        heartbeat_interval_seconds=int(os.getenv("SBOARD_HEARTBEAT_INTERVAL_SECONDS", "30")),
        offline_threshold_seconds=int(os.getenv("SBOARD_OFFLINE_THRESHOLD_SECONDS", "90")),
    )
