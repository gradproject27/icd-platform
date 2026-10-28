"""Platform settings read from the environment, with local-development defaults."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.api.schemas import DEFAULT_MAX_UPLOAD_MB


@dataclass(frozen=True)
class Settings:
    upload_dir: Path
    max_upload_bytes: int
    job_max_attempts: int
    worker_poll_seconds: float
    heartbeat_seconds: float
    lease_seconds: float


def _number(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return number


def get_settings() -> Settings:
    return Settings(
        upload_dir=Path(os.environ.get("UPLOAD_DIR") or "/data/uploads"),
        max_upload_bytes=int(_number("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB) * 1024 * 1024),
        job_max_attempts=int(_number("JOB_MAX_ATTEMPTS", 3)),
        worker_poll_seconds=_number("WORKER_POLL_SECONDS", 1),
        heartbeat_seconds=_number("WORKER_HEARTBEAT_SECONDS", 5),
        lease_seconds=_number("WORKER_LEASE_SECONDS", 60),
    )
