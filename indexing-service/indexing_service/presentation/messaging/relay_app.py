"""FastStream-приложение relay: публикует outbox-команды в RabbitMQ.

Запуск: ``faststream run \
indexing_service.presentation.messaging.relay_app:app``. Стратегия — polling
(источник истины — таблица outbox). Отдельный процесс от консюмера каталога.
"""

import asyncio
import contextlib

from faststream import FastStream

from indexing_service.bootstrap import build_relay
from indexing_service.infrastructure.config import get_settings
from indexing_service.infrastructure.messaging.broker import EMBEDDING_JOBS

_deps = build_relay(get_settings())
app = FastStream(_deps.broker)
_tasks: set[asyncio.Task] = set()


async def _relay_loop() -> None:
    while True:
        with contextlib.suppress(Exception):
            await _deps.publisher.drain_all()
        await asyncio.sleep(_deps.interval)


@app.after_startup
async def _start_relay() -> None:
    await _deps.broker.declare_exchange(EMBEDDING_JOBS)
    task = asyncio.create_task(_relay_loop())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
