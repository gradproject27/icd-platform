"""Duplicate-upload guard (C2, Week 4 item; decided 16 Nov 2026).

An upload is a duplicate when an earlier upload has the same SHA-256 and the same dataset_id
and its ingest job has not failed. POST /uploads then refuses it with 409 `duplicate_upload`
and points to the earlier upload, so the same file never gives two sets of incidents. A failed
earlier upload does not count, so the analyst can always retry after a failure.

Two identical uploads at the same moment are serialised by a transaction-level advisory lock on
the hash, so exactly one of them is accepted.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import JobKind, JobState
from app.models import JobRow, UploadRow


class DuplicateUpload(Exception):
    def __init__(self, upload_id: str) -> None:
        super().__init__(upload_id)
        self.upload_id = upload_id


def lock_and_find_duplicate(session: Session, sha256: str, dataset_id: str) -> str | None:
    """The earlier upload this file duplicates, or None. Call inside the insert transaction."""
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(sha256, 0))))
    return session.scalar(
        select(UploadRow.upload_id)
        .join(JobRow, JobRow.upload_id == UploadRow.upload_id)
        .where(
            UploadRow.sha256 == sha256,
            UploadRow.dataset_id == dataset_id,
            JobRow.kind == JobKind.INGEST.value,
            JobRow.state != JobState.FAILED.value,
        )
        .order_by(UploadRow.received_at, UploadRow.upload_id)
        .limit(1)
    )
