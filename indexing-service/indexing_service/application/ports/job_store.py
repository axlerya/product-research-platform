"""Порты хранилища jobs/requests (write-side, в границе UoW)."""

from typing import Protocol

from indexing_service.domain.entities.embedding_request import EmbeddingRequest
from indexing_service.domain.entities.indexing_job import IndexingJob
from indexing_service.domain.value_objects.identifiers import (
    JobId,
    ProductId,
    RequestId,
)


class IndexingJobRepository(Protocol):
    """Хранилище агрегата ``IndexingJob``."""

    async def upsert(self, job: IndexingJob) -> None:
        """Идемпотентно сохраняет job (по ``job_id``)."""
        ...

    async def get(self, job_id: JobId) -> IndexingJob | None:
        """Возвращает job по идентификатору или ``None``."""
        ...

    async def get_by_product(
        self, product_id: ProductId, content_version: int
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
