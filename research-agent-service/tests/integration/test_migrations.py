"""Интеграционные тесты миграций Alembic (PostgreSQL в контейнере).

Тесты синхронные: alembic-команды внутри env.py вызывают asyncio.run, что
несовместимо с уже запущенным циклом async-теста. Общий контейнер изолируется
пересозданием схемы public перед каждым тестом.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, create_engine, inspect

from research_agent_service.infrastructure.db import models  # noqa: F401
from research_agent_service.infrastructure.db.base import Base

pytestmark = pytest.mark.integration

_TABLES = {
    "conversations",
    "messages",
    "agent_runs",
    "tool_calls",
    "feedback",
    "outbox_events",
}


@pytest.fixture
def clean_db(postgres_url: str) -> str:
    """Пересоздаёт пустую схему public; возвращает async-URL для alembic."""
    sync_url = postgres_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP SCHEMA public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()
    return postgres_url


def _config(async_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", async_url)
    return config


def _table_names(async_url: str) -> set[str]:
    engine = create_engine(async_url.replace("+asyncpg", "+psycopg2"))
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_all_tables(clean_db: str) -> None:
    """upgrade head поднимает все таблицы схемы."""
    upgrade(_config(clean_db), "head")

    assert _TABLES <= _table_names(clean_db)


def test_migration_matches_models(clean_db: str) -> None:
    """После upgrade head автосравнение с моделями не даёт расхождений."""
    upgrade(_config(clean_db), "head")

    engine = create_engine(clean_db.replace("+asyncpg", "+psycopg2"))
    try:
        with engine.connect() as connection:
            diff = _diff(connection)
    finally:
        engine.dispose()

    assert diff == []


def test_downgrade_drops_all_tables(clean_db: str) -> None:
    """downgrade base убирает все таблицы схемы."""
    config = _config(clean_db)
    upgrade(config, "head")
    downgrade(config, "base")

    assert _TABLES.isdisjoint(_table_names(clean_db))


def _diff(connection: Connection) -> list:
    context = MigrationContext.configure(
        connection, opts={"compare_type": True}
    )
    return compare_metadata(context, Base.metadata)
