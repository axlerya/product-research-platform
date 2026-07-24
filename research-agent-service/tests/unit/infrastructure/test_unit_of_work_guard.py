"""Юнит-тесты UnitOfWork: защита и изоляция сессий (без БД)."""

import asyncio
import itertools

import pytest

from research_agent_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


class _FakeSession:
    """Сессия-заглушка с меткой для проверки изоляции."""

    def __init__(self, tag: int) -> None:
        self.tag = tag
        self.closed = False

    async def rollback(self) -> None: ...

    async def close(self) -> None:
        self.closed = True


async def test_commit_without_open_raises() -> None:
    """commit() до входа в контекст → ошибка."""
    uow = SqlAlchemyUnitOfWork(session_factory=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        await uow.commit()


async def test_concurrent_transactions_get_isolated_sessions() -> None:
    """Один UnitOfWork, две конкурентные задачи — каждая на своей сессии."""
    counter = itertools.count()
    created: list[_FakeSession] = []

    def factory() -> _FakeSession:
        session = _FakeSession(next(counter))
        created.append(session)
        return session

    uow = SqlAlchemyUnitOfWork(session_factory=factory)  # type: ignore[arg-type]

    async def transaction() -> tuple[int, int]:
        async with uow:
            before = uow._require_session().tag
            await asyncio.sleep(0)  # уступаем управление другой задаче
            after = uow._require_session().tag
            return before, after

    first, second = await asyncio.gather(transaction(), transaction())

    # внутри задачи метка сессии стабильна, несмотря на чередование
    assert first[0] == first[1]
    assert second[0] == second[1]
    # у задач разные сессии
    assert first[0] != second[0]
    # обе сессии закрыты
    assert all(session.closed for session in created)
