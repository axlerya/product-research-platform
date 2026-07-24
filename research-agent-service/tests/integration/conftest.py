"""Фикстуры интеграционных тестов: PostgreSQL в контейнере."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

from research_agent_service.infrastructure.db import models  # noqa: F401
from research_agent_service.infrastructure.db.base import Base
from research_agent_service.infrastructure.db.engine import (
    build_engine,
    build_session_factory,
)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Поднимает Postgres в контейнере, отдаёт asyncpg-URL."""
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url()
        yield url.replace("+psycopg2", "+asyncpg")


@pytest_asyncio.fixture
async def session_factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Свежая схема на каждый тест (drop/create), фабрика сессий."""
    engine = build_engine(postgres_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield build_session_factory(engine)
    await engine.dispose()
