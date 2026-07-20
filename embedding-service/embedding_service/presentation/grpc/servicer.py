"""gRPC-servicer ``EmbeddingService`` — тонкий адаптер над U2/U3 (§6).

Обязательный deadline проверяется до инференса; fail-fast на невалидном
входе; прикладные исключения отображаются в gRPC status codes.
"""

import grpc

from embedding_service.application.dto import (
    EmbedQueriesQuery,
    EmbedQueryQuery,
)
from embedding_service.application.exceptions import ApplicationError
from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc as rpc,
)
from embedding_service.presentation.grpc.mappers import to_query_embedding
from embedding_service.presentation.grpc.status_map import to_status_code


class EmbeddingServicer(rpc.EmbeddingServiceServicer):
    """Реализация gRPC-сервиса поверх use cases EmbedQuery/EmbedQueries."""

    def __init__(
        self,
        embed_query: EmbedQuery,
        embed_queries: EmbedQueries,
        *,
        deadline_guard_s: float = 0.005,
    ) -> None:
        self._embed_query = embed_query
        self._embed_queries = embed_queries
        self._deadline_guard_s = deadline_guard_s

    async def EmbedQuery(
        self,
        request: pb.EmbedQueryRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.EmbedQueryResponse:
        await self._guard_deadline(context)
        if not request.text.strip():
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "empty text")
        try:
            result = await self._embed_query.handle(
                EmbedQueryQuery(
                    text=request.text, request_id=request.request_id or None
                )
            )
        except ApplicationError as exc:
            await context.abort(to_status_code(exc), str(exc))
        embedding = result.embedding
        return pb.EmbedQueryResponse(
            embedding=to_query_embedding(embedding, result.token_count),
            model_version=embedding.model_id.key,
            dim=embedding.model_id.dim,
        )

    async def EmbedQueries(
        self,
        request: pb.EmbedQueriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.EmbedQueriesResponse:
        await self._guard_deadline(context)
        try:
            batch = await self._embed_queries.handle(
                EmbedQueriesQuery(
                    texts=tuple(request.texts),
                    request_id=request.request_id or None,
                )
            )
        except ApplicationError as exc:
            await context.abort(to_status_code(exc), str(exc))
        return pb.EmbedQueriesResponse(
            embeddings=[
                to_query_embedding(item.embedding, item.token_count)
                for item in batch.items
            ],
            model_version=batch.model_id.key,
            dim=batch.model_id.dim,
        )

    async def _guard_deadline(self, context: grpc.aio.ServicerContext) -> None:
        remaining = context.time_remaining()
        if remaining is not None and remaining <= self._deadline_guard_s:
            await context.abort(
                grpc.StatusCode.DEADLINE_EXCEEDED,
                "insufficient time budget for inference",
            )
