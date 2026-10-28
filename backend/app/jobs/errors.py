"""Exceptions a job runner raises to end a job."""

from app.api.schemas import ErrorCode


class JobFailure(Exception):
    """End the job as failed with this code and plain-language message."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JobLost(Exception):
    """This worker no longer holds the job (it was reaped). Stop without writing anything."""
