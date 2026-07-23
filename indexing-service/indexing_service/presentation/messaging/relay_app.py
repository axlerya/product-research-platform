"""ASGI-приложение relay: публикует outbox-команды в RabbitMQ (§9.6).

Запуск: ``uvicorn
indexing_service.presentation.messaging.relay_app:app``. Стратегия —
polling (источник истины — таблица outbox). Отдельный процесс от консюмеров.

Тот же цикл переснимает метрики отставания: relay и так ходит в outbox
каждую итерацию, а больше эти gauge'и снимать некому.
"""

import asyncio
import contextlib
import logging

from faststream.asgi import AsgiFastStream, make_ping_asgi
from prometheus_client import CollectorRegistry, make_asgi_app

from indexing_service.bootstrap import build_relay
from indexing_service.infrastructure.config import get_settings
from indexing_service.infrastructure.messaging.broker import EMBEDDING_JOBS

_logger = logging.getLogger(__name__)
_registry = CollectorRegistry()
_deps = build_relay(get_settings(), registry=_registry)
app = AsgiFastStream(
    _deps.broker,
    asgi_routes=[
        ("/health", make_ping_asgi(_deps.broker, timeout=5.0)),
        ("/metrics", make_asgi_app(_registry)),
    ],
)
_tasks: set[asyncio.Task] = set()


async def _relay_loop() -> None:
    while True:
        try:
            await _deps.publisher.drain_all()
            if _deps.gauges is not None:
                await _deps.gauges.refresh()
        except Exception:
            _logger.exception("сбой прохода relay")
        await asyncio.sleep(_deps.interval)


@app.after_startup
async def _start_relay() -> None:
    await _deps.broker.declare_exchange(EMBEDDING_JOBS)
    task = asyncio.create_task(_relay_loop())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@app.on_shutdown
async def _close_relay() -> None:
    for task in list(_tasks):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await _deps.aclose()
