"""Порт ``UnitOfWork`` — транзакционная граница {jobs + requests + outbox}.

Все три репозитория делят одну сессию, поэтому job, команда и строка outbox
коммитятся атомарно одним ``commit()`` (transactional outbox).
"""

from types import TracebackType
from typing import Protocol

from indexing_service.application.ports.job_store import (
    EmbeddingRequestRepository,
    IndexingJobRepository,
)
from indexing_service.application.ports.outbox import OutboxRepository


class UnitOfWork(Protocol):
    """Единица работы: сессия + репозитории в одной транзакции."""

    jobs: IndexingJobRepository
    requests: EmbeddingRequestRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
