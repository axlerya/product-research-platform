"""GrpcRerankerClient — cross-encoder переранжирование (порт RerankerPort).

Коды UNIMPLEMENTED (reranker выключен) / UNAVAILABLE (не готов) /
DEADLINE_EXCEEDED (перегруз без backpressure) транслируются в
RerankerUnavailable — сигнал деградации до порядка RRF.
"""

from decimal import Decimal

import grpc

from research_agent_service.application.dto.retrieval import (
    RankedDoc,
    RerankDocument,
)
from research_agent_service.application.exceptions import RerankerUnavailable
from research_agent_service.infrastructure.grpc._generated import (
    reranker_pb2,
    reranker_pb2_grpc,
)

_DEFAULT_DEADLINE_S = 5.0
_DEGRADE_CODES = frozenset(
    {
        grpc.StatusCode.UNIMPLEMENTED,
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    }
)


class GrpcRerankerClient:
    """Клиент reranker.v1.RerankerService."""

    def __init__(
        self,
        *,
        stub: reranker_pb2_grpc.RerankerServiceStub,
        deadline_s: float = _DEFAULT_DEADLINE_S,
    ) -> None:
        self._stub = stub
        self._deadline_s = deadline_s

    async def rerank(
        self,
        query: str,
        documents: tuple[RerankDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RankedDoc, ...]:
        """Переранжирует документы; недоступность → RerankerUnavailable."""
        request = reranker_pb2.RerankRequest(
            query=query,
            documents=[
                reranker_pb2.RerankDocument(id=doc.id, text=doc.text)
                for doc in documents
            ],
            top_n=top_n,
            return_documents=False,
        )
        try:
            response = await self._stub.Rerank(
                request, timeout=self._deadline_s
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() in _DEGRADE_CODES:
                raise RerankerUnavailable(str(exc.code())) from exc
            raise
        return tuple(
            RankedDoc(
                id=item.id, index=item.index, score=Decimal(str(item.score))
            )
            for item in response.results
        )
