"""Тесты сериализации обработки по агрегату."""

import asyncio

from indexing_service.application.aggregate_lock import AggregateLock


async def _critical_section(
    lock: AggregateLock, key: str, log: list[str], tag: str
) -> None:
    """Секция с уступкой управления: без замка входы чередуются."""
    async with lock.acquire(key):
        log.append(f"{tag}:in")
        await asyncio.sleep(0)
        log.append(f"{tag}:out")


async def test_same_key_runs_sequentially() -> None:
    """Два события одного товара не пересекаются во времени."""
    lock = AggregateLock()
    log: list[str] = []

    await asyncio.gather(
        _critical_section(lock, "p1", log, "a"),
        _critical_section(lock, "p1", log, "b"),
    )

    assert log in (
        ["a:in", "a:out", "b:in", "b:out"],
        ["b:in", "b:out", "a:in", "a:out"],
    )


async def test_different_keys_run_concurrently() -> None:
    """Разные товары обрабатываются параллельно — замок их не связывает."""
    lock = AggregateLock()
    log: list[str] = []

    await asyncio.gather(
        _critical_section(lock, "p1", log, "a"),
        _critical_section(lock, "p2", log, "b"),
    )

    assert log == ["a:in", "b:in", "a:out", "b:out"]


async def test_locks_are_released_after_use() -> None:
    """Замки не накапливаются: словарь пуст после выхода из секций."""
    lock = AggregateLock()

    await asyncio.gather(
        *(_critical_section(lock, f"p{i}", [], str(i)) for i in range(20))
    )

    assert lock.tracked() == 0


async def test_lock_survives_failure_inside_section() -> None:
    """Исключение внутри секции освобождает замок, а не запирает товар."""
    lock = AggregateLock()

    try:
        async with lock.acquire("p1"):
            raise ValueError("сбой обработки")
    except ValueError:
        pass

    assert lock.tracked() == 0
    async with lock.acquire("p1"):
        pass


async def test_waiting_task_keeps_lock_alive() -> None:
    """Пока кто-то ждёт, замок не выбрасывается и очередь сохраняется."""
    lock = AggregateLock()
    log: list[str] = []

    async def slow() -> None:
        async with lock.acquire("p1"):
            log.append("slow:in")
            await asyncio.sleep(0.05)
            log.append("slow:out")

    async def fast() -> None:
        await asyncio.sleep(0)
        async with lock.acquire("p1"):
            log.append("fast:in")

    await asyncio.gather(slow(), fast())

    assert log == ["slow:in", "slow:out", "fast:in"]
