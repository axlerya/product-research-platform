"""Порт VectorSearchPort — read-only гибридный поиск в Qdrant (RRF)."""

from typing import Protocol

from research_agent_service.application.dto.retrieval import RetrievedPoint
from research_agent_service.domain.value_objects.query import QueryFilters


class VectorSearchPort(Protocol):
    """Только чтение: гибридный dense+sparse поиск с серверным RRF."""

    async def hybrid_search(
        self,
        *,
        dense: tuple[float, ...],
        sparse_indices: tuple[int, ...],
        sparse_values: tuple[float, ...],
        filters: QueryFilters | None,
        limit: int,
    ) -> tuple[RetrievedPoint, ...]:
        """Возвращает до ``limit`` точек, слитых по RRF (без записи)."""
        ...
