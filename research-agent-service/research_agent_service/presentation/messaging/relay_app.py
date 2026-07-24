"""Runner relay outbox (FastStream) — публикация событий (вне покрытия).

Отдельный процесс от API: периодически дренирует outbox в RabbitMQ. Запуск:
faststream run research_agent_service.presentation.messaging.relay_app:app
"""

import asyncio

from faststream import FastStream
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_agent_service.infrastructure.config import Settings, get_settings
from research_agent_service.infrastructure.db.engine import (
    build_engine,
    build_session_factory,
)
from research_agent_service.infrastructure.messaging.rabbitmq import (
    RabbitEventPublisher,
    build_broker,
    build_exchange,
)
from research_agent_service.infrastructure.outbox.relay import OutboxPublisher

_TASKS: set[asyncio.Task[None]] = set()


async def _drain_loop(
    relay: OutboxPublisher,
    session_factory: async_sessionmaker[AsyncSession],
    interval_s: float,
) -> None:
    while True:
        async with session_factory() as session:
            await relay.drain_all(session)
        await asyncio.sleep(interval_s)


def build_relay_app(settings: Settings) -> FastStream:
    """Строит FastStream-приложение relay'я outbox."""
    broker = build_broker(settings.rabbitmq_dsn)
    exchange = build_exchange()
    relay = OutboxPublisher(
        publisher=RabbitEventPublisher(broker=broker, exchange=exchange),
        batch_size=settings.relay_batch_size,
    )
    session_factory = build_session_factory(build_engine(settings.database_url))
    app = FastStream(broker)

    @app.after_startup
    async def _start() -> None:
        await broker.declare_exchange(exchange)
        task = asyncio.create_task(
            _drain_loop(relay, session_factory, settings.relay_interval_s)
        )
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)

    return app


app = build_relay_app(get_settings())
