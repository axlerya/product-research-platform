"""FastStream-приложение relay: публикует outbox в RabbitMQ.

Запуск: ``faststream run \
catalog_service.presentation.messaging.relay_app:app``.
Стратегия — polling (источник истины — таблица outbox); NOTIFY-триггер из
миграции 0002 — задел под низколатентный вариант.
"""

import asyncio
import contextlib

from faststream import FastStream

from catalog_service.bootstrap import build_container
from catalog_service.infrastructure.messaging.broker import CATALOG_EVENTS

_container = build_container()
app = FastStream(_container.broker)
_tasks: set[asyncio.Task] = set()


async def _relay_loop() -> None:
    publisher = _container.outbox_publisher()
    interval = _container.settings.outbox_poll_interval_s
    while True:
        with contextlib.suppress(Exception):
            await publisher.drain_all()
        await asyncio.sleep(interval)


@app.after_startup
async def _start_relay() -> None:
    await _container.broker.declare_exchange(CATALOG_EVENTS)
    task = asyncio.create_task(_relay_loop())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
