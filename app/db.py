"""Database initialization and session generator for DocuMind."""

from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)


def init_db() -> None:
    """Creates all database tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_db() -> Generator[DBSession, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    with DBSession(engine) as session:
        yield session
