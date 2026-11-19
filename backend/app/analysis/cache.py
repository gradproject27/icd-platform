"""Report cache (AI1, workflow step 11): never analyse the same evidence twice with the same setup.

    key = cache_key(evidence, prompt_version, model_id)

The key is the SHA-256 of one canonical JSON document holding the masked evidence package
(without `created_at`, which changes on every build), the prompt version and the model pin. The
same incident with the same events, risk and masking, sent with the same prompt to the same
model, always gets the same key; a change to any of them gives a new key, so a stale report is
never reused. Only valid reports are cached: a failed analysis is tried again next time.

Two stores share one interface: `FileReportCache` (a folder, for the runbook and the cluster)
and `app.analysis.store.DbReportCache` (the `analysis_reports` table, for the platform).
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.contracts import AnalysisReport, EvidencePackage

CACHE_KEY_VERSION = "ai1-cache-v1"
# Fields of the package left out of the key: they change on every build, not with the evidence.
VOLATILE_PACKAGE_FIELDS = {"created_at"}


def cache_document(evidence: EvidencePackage, prompt_version: str, model_id: str) -> str:
    """The exact text that is hashed. Sorted keys and no spaces, so it is the same everywhere."""
    if not evidence.masked:
        raise ValueError("only masked evidence packages are cached (NFR-S-07)")
    document = {
        "key_version": CACHE_KEY_VERSION,
        "evidence_package": evidence.model_dump(mode="json", exclude=VOLATILE_PACKAGE_FIELDS),
        "prompt_version": prompt_version,
        "model": model_id,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(evidence: EvidencePackage, prompt_version: str, model_id: str) -> str:
    """SHA-256 of the masked package, the prompt version and the model pin, lower-case hex."""
    text = cache_document(evidence, prompt_version, model_id)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    """One valid report and how it was made."""

    key: str
    report: AnalysisReport
    raw_output: str | None
    stored_at: datetime


class ReportCache(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...

    def put(self, entry: CacheEntry) -> None: ...


class MemoryReportCache:
    """For tests and single runs."""

    def __init__(self) -> None:
        self.entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> CacheEntry | None:
        return self.entries.get(key)

    def put(self, entry: CacheEntry) -> None:
        self.entries[entry.key] = entry


class FileReportCache:
    """One JSON file per key: <root>/<first 2 hex digits>/<key>.json. A later put replaces it."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("a cache key is 64 lower-case hex digits")
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> CacheEntry | None:
        path = self.path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("key") != key:
            return None
        return CacheEntry(
            key=key,
            report=AnalysisReport.model_validate(data["report"]),
            raw_output=data.get("raw_output"),
            stored_at=datetime.fromisoformat(data["stored_at"]),
        )

    def put(self, entry: CacheEntry) -> None:
        path = self.path(entry.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "key": entry.key,
            "key_version": CACHE_KEY_VERSION,
            "stored_at": entry.stored_at.isoformat(),
            "report": entry.report.model_dump(mode="json"),
            "raw_output": entry.raw_output,
        }
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
