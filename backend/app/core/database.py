from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.config import Settings, get_settings


def make_engine(settings: Settings | None = None) -> Engine:
    active_settings = settings or get_settings()
    return create_engine(active_settings.database_url, pool_pre_ping=True)


engine = make_engine()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
