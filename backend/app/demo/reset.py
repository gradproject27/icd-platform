"""Empty the platform for a demo run (C1, roadmap task 26, decision F9).

    ICD_ALLOW_RESET=1 python -m app.demo.reset

Empties every application table (the schema and alembic_version stay, so no migration runs
again) and deletes the stored uploaded files. It refuses to run unless ICD_ALLOW_RESET=1, so
it cannot wipe a database by accident. Stop the worker first (tools/c1/demo_reset.py does).
"""

import os
import sys
from pathlib import Path

from sqlalchemy import Engine, text

KEEP = {"alembic_version"}


def app_tables(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        names = connection.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
        ).all()
    return sorted(n for n in names if n not in KEEP)


def reset(engine: Engine, upload_dir: Path) -> tuple[list[str], int]:
    """Empty the tables and the upload directory. Returns (tables emptied, files deleted)."""
    tables = app_tables(engine)
    if tables:
        quoted = ", ".join(f'"{name}"' for name in tables)
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    deleted = 0
    if upload_dir.is_dir():
        for path in upload_dir.iterdir():
            if path.is_file():
                path.unlink()
                deleted += 1
    return tables, deleted


def main() -> int:
    if os.environ.get("ICD_ALLOW_RESET") != "1":
        print("refused: set ICD_ALLOW_RESET=1 to empty this database", file=sys.stderr)
        return 2
    from app.db import get_engine
    from app.settings import get_settings

    tables, deleted = reset(get_engine(), get_settings().upload_dir)
    print(f"emptied {len(tables)} tables; deleted {deleted} uploaded files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
