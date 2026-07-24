"""Порт RerankerPort — cross-encoder переранжирование (embedding-service)."""

from typing import Protocol

from research_agent_service.application.dto.retrieval import (
    RankedDoc,
    RerankDocument,
)


class RerankerPort(Protocol):
    """Переранжирование кандидатов по релевантности запросу."""

    async def rerank(
        self,
        query: str,
        documents: tuple[RerankDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RankedDoc, ...]:
        """Ранжирует документы; при недоступности — ``RerankerUnavailable``."""
        ...
