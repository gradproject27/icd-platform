"""Database engine and declarative base.

The engine is created lazily on first use, so the app imports and starts even when
DATABASE_URL is unset (for example in unit tests without a database).
"""

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for ORM models. Alembic reads Base.metadata."""


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


def check_database() -> bool:
    """Return True if `SELECT 1` succeeds, False if the database is unreachable."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except (RuntimeError, SQLAlchemyError):
        return False
    return True
