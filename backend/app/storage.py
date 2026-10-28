"""Uploaded files on the shared volume (decision D4).

A file is stored under its upload_id, never under the name the user gave it, so a crafted
file name cannot reach another path. It is written to <upload_id>.part first and renamed
only when complete, so the worker never sees half a file.
"""

import hashlib
from pathlib import Path
from typing import Protocol

CHUNK_BYTES = 1024 * 1024


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class TooLarge(Exception):
    pass


def stored_path(upload_dir: Path, upload_id: str) -> Path:
    return upload_dir / upload_id


async def save_stream(
    source: AsyncReadable, upload_dir: Path, upload_id: str, max_bytes: int
) -> tuple[int, str]:
    """Copy the upload to disk. Returns (size in bytes, SHA-256 hex). Raises TooLarge."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    final = stored_path(upload_dir, upload_id)
    partial = final.with_name(f"{upload_id}.part")
    digest = hashlib.sha256()
    size = 0
    try:
        with partial.open("wb") as out:
            while chunk := await source.read(CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise TooLarge
                digest.update(chunk)
                out.write(chunk)
        partial.replace(final)
    finally:
        partial.unlink(missing_ok=True)
    return size, digest.hexdigest()


def delete_stored(upload_dir: Path, upload_id: str) -> None:
    stored_path(upload_dir, upload_id).unlink(missing_ok=True)
