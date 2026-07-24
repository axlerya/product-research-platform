"""Порт EmbeddingPort — dense+sparse эмбеддинг запроса (embedding-service)."""

from typing import Protocol

from research_agent_service.application.dto.retrieval import QueryEmbedding


class EmbeddingPort(Protocol):
    """Синхронный эмбеддинг поисковых запросов."""

    async def embed_query(self, text: str) -> QueryEmbedding:
        """Возвращает dense+sparse эмбеддинг одного запроса."""
        ...
