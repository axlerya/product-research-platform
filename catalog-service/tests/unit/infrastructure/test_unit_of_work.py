"""Тесты ``SqlAlchemyUnitOfWork`` и outbox-репозитория без БД."""

import pytest

from catalog_service.infrastructure.db.repositories import (
    SqlAlchemyOutboxRepository,
)
from catalog_service.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


async def test_commit_delegates_and_closes():
    session = _FakeSession()
    uow = SqlAlchemyUnitOfWork(lambda: session)
    async with uow:
        await uow.commit()
    assert session.committed is True
    assert session.closed is True


async def test_rolls_back_on_exception():
    session = _FakeSession()
    uow = SqlAlchemyUnitOfWork(lambda: session)
    with pytest.raises(ValueError, match="boom"):
        async with uow:
            raise ValueError("boom")
    assert session.rolled_back is True
    assert session.closed is True


async def test_explicit_rollback_delegates():
    session = _FakeSession()
    uow = SqlAlchemyUnitOfWork(lambda: session)
    async with uow:
        await uow.rollback()
    assert session.rolled_back is True


async def test_outbox_add_many_empty_is_noop():
    # Пустой список не трогает сессию (session не нужен).
    await SqlAlchemyOutboxRepository(session=None).add_many([])
