"""Тесты фабрик движка и сессий (без подключения к БД)."""

from sqlalchemy.ext.asyncio import AsyncEngine

from catalog_service.infrastructure.config import Settings
from catalog_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)


def test_build_engine_and_sessionmaker():
    engine = build_engine(Settings())
    assert isinstance(engine, AsyncEngine)
    assert build_sessionmaker(engine) is not None
