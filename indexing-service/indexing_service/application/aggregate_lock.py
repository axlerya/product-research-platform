"""Сериализация обработки по агрегату.

Обработка события каталога — это read-modify-write водяного знака: сначала
читаем версию точки, потом решаем действие, потом пишем. Guard по версии
корректен только если между чтением и записью никто не вклинился с другим
событием того же товара — иначе более старое событие затирает более новое, и
расхождение с каталогом остаётся навсегда (следующих событий уже не будет).

Полагаться на то, что консюмер не запускает обработчики параллельно, нельзя:
это деталь брокера и фреймворка. Поэтому инвариант «одно событие товара за
раз» удерживается здесь явно. Разные товары по-прежнему обрабатываются
параллельно.
"""

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager


class AggregateLock:
    """Замки по ключу агрегата с очисткой неиспользуемых."""

    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._waiters: dict[Hashable, int] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        """Захватывает замок ключа на время блока."""
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        # Считаем ожидающих: замок нельзя выбросить, пока на него кто-то
        # смотрит, иначе следующий вошедший создаст второй и сериализация
        # развалится.
        self._waiters[key] = self._waiters.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._waiters[key] -= 1
            if not self._waiters[key]:
                del self._waiters[key]
                del self._locks[key]

    def tracked(self) -> int:
        """Сколько замков сейчас удерживается (для тестов и метрик)."""
        return len(self._locks)
