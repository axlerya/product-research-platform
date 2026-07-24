"""Асинхронный движок и фабрика сессий SQLAlchemy."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(url: str) -> AsyncEngine:
    """Создаёт асинхронный движок к PostgreSQL."""
    return create_async_engine(url, pool_pre_ping=True)


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий (expire_on_commit=False — объекты живут после commit)."""
    return async_sessionmaker(engine, expire_on_commit=False)
