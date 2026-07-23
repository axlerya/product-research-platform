"""Порты хранилища jobs/requests (write-side, в границе UoW)."""

from datetime import datetime
from typing import Protocol

from indexing_service.domain.entities.embedding_request import EmbeddingRequest
from indexing_service.domain.entities.indexing_job import IndexingJob
from indexing_service.domain.value_objects.identifiers import (
    JobId,
    ProductId,
    RequestId,
)
from indexing_service.domain.value_objects.job_status import JobStatus


class IndexingJobRepository(Protocol):
    """Хранилище агрегата ``IndexingJob``."""

    async def upsert(self, job: IndexingJob) -> None:
        """Идемпотентно сохраняет job (по ``job_id``)."""
        ...

    async def get(self, job_id: JobId) -> IndexingJob | None:
        """Возвращает job по идентификатору или ``None``."""
        ...

    async def epoch_counts(
        self, target_collection: str
    ) -> dict[JobStatus, int]:
        """Считает задания целевой коллекции по статусам (Q6)."""
        ...

    async def get_by_product(
        self,
        product_id: ProductId,
        content_version: int,
        target_collection: str | None = None,
    ) -> IndexingJob | None:
        """Возвращает job товара на данной версии текста или ``None``."""
        ...


class EmbeddingRequestRepository(Protocol):
    """Хранилище команд ``EmbeddingRequest`` (дочерних к job)."""

    async def add(self, request: EmbeddingRequest) -> None:
        """Добавляет команду."""
        ...

    async def get(self, request_id: RequestId) -> EmbeddingRequest | None:
        """Возвращает команду по идентификатору или ``None``."""
        ...

    async def update(self, request: EmbeddingRequest) -> None:
        """Обновляет статус/времена команды."""
        ...

    async def find_stale(
        self, older_than: datetime, *, limit: int = 100
    ) -> list[EmbeddingRequest]:
        """Команды без ответа дольше таймаута (§10)."""
        ...
