"""Database engine, session factory, and initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base

_DB_PATH = Path(__file__).parent / "trend_trading.db"
_engine = None


def get_engine(url: Optional[str] = None):
    """Create or return the SQLAlchemy engine.

    Args:
        url: Optional database URL. Defaults to sqlite:///db/trend_trading.db.
    """
    global _engine
    if _engine is None or url is not None:
        if url is None:
            url = f"sqlite:///{_DB_PATH}"
        _engine = create_engine(url, echo=False)
    return _engine


def get_session(engine=None) -> Session:
    """Return a new Session bound to the given or default engine."""
    if engine is None:
        engine = get_engine()
    return Session(engine)


def init_db(engine=None):
    """Create all tables from Base.metadata."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
