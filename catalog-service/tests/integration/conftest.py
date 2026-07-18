"""Фикстуры integration-тестов: Postgres (testcontainers) + Alembic.

Схема накатывается настоящими миграциями (артефакт деплоя), а не
``create_all``. Перед каждым тестом таблицы очищаются.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("+psycopg2", "+asyncpg")


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(database_url: str) -> None:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def sm(database_url: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE products, outbox, categories, brands, suppliers "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()
