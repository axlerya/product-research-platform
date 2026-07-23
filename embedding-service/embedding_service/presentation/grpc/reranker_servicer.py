"""gRPC-servicer ``RerankerService`` — тонкий адаптер над ``RerankDocuments``.

Обязательный deadline проверяется до инференса; невыгретый/деградировавший
reranker → ``UNAVAILABLE``; прикладные исключения → gRPC status codes
(переиспользуется общий ``status_map``). Изолирован от ``EmbeddingServicer``.
"""

from collections.abc import Callable

import grpc

from embedding_service.application.exceptions import ApplicationError
from embedding_service.application.use_cases.rerank_documents import (
    RerankDocuments,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2_grpc as rpc,
)
from embedding_service.presentation.grpc.reranker_mappers import (
    to_rerank_command,
    to_rerank_response,
)
from embedding_service.presentation.grpc.status_map import to_status_code


class RerankerServicer(rpc.RerankerServiceServicer):
    """Реализация gRPC reranker поверх use case ``RerankDocuments``.

    ``rerank_documents`` допускает ``None`` — случай, когда провайдер не
    создался и сервис зарегистрирован лишь для того, чтобы отвечать
    ``UNAVAILABLE`` вместо ``UNIMPLEMENTED``. Инвариант: ``is_ready() is True``
    ⇒ use case присутствует (готовность выставляется только после успешного
    прогрева), поэтому до ``self._rerank`` запрос доходит только с ним.
    """

    def __init__(
        self,
        rerank_documents: RerankDocuments | None,
        is_ready: Callable[[], bool],
        *,
        deadline_guard_s: float = 0.005,
    ) -> None:
        self._rerank = rerank_documents
        self._is_ready = is_ready
        self._deadline_guard_s = deadline_guard_s

    async def Rerank(
        self,
        request: pb.RerankRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.RerankResponse:
        await self._guard_deadline(context)
        if not self._is_ready():
            await context.abort(
                grpc.StatusCode.UNAVAILABLE, "reranker не готов"
            )
        try:
            result = await self._rerank.handle(to_rerank_command(request))
        except ApplicationError as exc:
            await context.abort(to_status_code(exc), str(exc))
        return to_rerank_response(request, result)

    async def _guard_deadline(self, context: grpc.aio.ServicerContext) -> None:
        remaining = context.time_remaining()
        if remaining is not None and remaining <= self._deadline_guard_s:
            await context.abort(
                grpc.StatusCode.DEADLINE_EXCEEDED,
                "insufficient time budget for inference",
            )
