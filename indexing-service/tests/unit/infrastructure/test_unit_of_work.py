"""Юнит-тесты UnitOfWork: защита и изоляция сессий (без БД).

Консюмер держит один экземпляр use case (а значит и один UnitOfWork) и
обрабатывает события конкурентно: подписчиков на очереди двое, prefetch
больше единицы. Сессия на экземпляре в таком режиме разъезжается — отсюда
``Session is already flushing`` и залипшие в pending задания.
"""

import asyncio
import itertools

import pytest

from indexing_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


class _FakeSession:
    """Сессия-заглушка с меткой для проверки изоляции."""

    def __init__(self, tag: int) -> None:
        self.tag = tag
        self.closed = False
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


def _factory(created: list[_FakeSession]):
    counter = itertools.count()

    def make() -> _FakeSession:
        session = _FakeSession(next(counter))
        created.append(session)
        return session

    return make


async def test_commit_without_open_raises() -> None:
    """commit() до входа в контекст → ошибка, а не тихая работа на None."""
    uow = SqlAlchemyUnitOfWork(None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        await uow.commit()


async def test_concurrent_transactions_get_isolated_sessions() -> None:
    """Один UnitOfWork, две конкурентные задачи — каждая на своей сессии."""
    created: list[_FakeSession] = []
    uow = SqlAlchemyUnitOfWork(_factory(created))  # type: ignore[arg-type]

    async def transaction() -> tuple[int, int]:
        async with uow:
            before = uow.jobs._session.tag
            await asyncio.sleep(0)  # уступаем управление другой задаче
            after = uow.jobs._session.tag
            return before, after

    first, second = await asyncio.gather(transaction(), transaction())

    assert first[0] == first[1]
    assert second[0] == second[1]
    assert first[0] != second[0]
    assert all(session.closed for session in created)


async def test_repositories_share_one_session_within_transaction() -> None:
    """Внутри одной транзакции репозитории работают на общей сессии."""
    created: list[_FakeSession] = []
    uow = SqlAlchemyUnitOfWork(_factory(created))  # type: ignore[arg-type]

    async with uow:
        tags = {uow.jobs._session.tag, uow.requests._session.tag}
        tags.add(uow.outbox._session.tag)

    assert len(tags) == 1


async def test_failed_transaction_rolls_back_and_closes() -> None:
    """Исключение внутри блока откатывает и закрывает сессию."""
    created: list[_FakeSession] = []
    uow = SqlAlchemyUnitOfWork(_factory(created))  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        async with uow:
            raise ValueError("сбой обработки события")

    assert created[0].rolled_back is True
    assert created[0].closed is True
