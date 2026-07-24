"""Юнит-тест защиты UnitOfWork (без БД)."""

import pytest

from research_agent_service.infrastructure.db.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


async def test_commit_without_open_raises() -> None:
    """commit() до входа в контекст → ошибка."""
    uow = SqlAlchemyUnitOfWork(session_factory=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        await uow.commit()
