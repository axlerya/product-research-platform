"""Async-движок SQLAlchemy и фабрика сессий."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from catalog_service.infrastructure.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Создаёт async-движок с пулом соединений."""
    return create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=settings.sql_echo,
    )


def build_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker:
    """Создаёт фабрику сессий.

    ``expire_on_commit=False`` — объекты пригодны после commit; ``autoflush``
    отключён ради контролируемого порядка flush (outbox-паттерн).
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
