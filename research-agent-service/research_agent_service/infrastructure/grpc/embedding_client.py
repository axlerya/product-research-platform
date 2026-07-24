"""GrpcEmbeddingClient — dense+sparse эмбеддинг запроса (порт EmbeddingPort).

Каждый вызов несёт обязательный дедлайн (контракт embedding-service).
"""

from research_agent_service.application.dto.retrieval import QueryEmbedding
from research_agent_service.infrastructure.grpc._generated import (
    embedding_pb2,
    embedding_pb2_grpc,
)

_DEFAULT_DEADLINE_S = 1.5


class GrpcEmbeddingClient:
    """Клиент embedding.v1.EmbeddingService."""

    def __init__(
        self,
        *,
        stub: embedding_pb2_grpc.EmbeddingServiceStub,
        deadline_s: float = _DEFAULT_DEADLINE_S,
    ) -> None:
        self._stub = stub
        self._deadline_s = deadline_s

    async def embed_query(self, text: str) -> QueryEmbedding:
        """Возвращает dense+sparse эмбеддинг одного запроса."""
        request = embedding_pb2.EmbedQueryRequest(text=text)
        response = await self._stub.EmbedQuery(
            request, timeout=self._deadline_s
        )
        embedding = response.embedding
        return QueryEmbedding(
            dense=tuple(embedding.dense.values),
            sparse_indices=tuple(embedding.sparse.indices),
            sparse_values=tuple(embedding.sparse.values),
            model_version=response.model_version,
            token_count=embedding.token_count,
        )
