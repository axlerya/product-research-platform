"""Маппинг proto ↔ application/domain для reranker (RerankRequest/Response)."""

from embedding_service.application.dto.reranking import (
    RerankDocumentsCommand,
    RerankInputDocument,
)
from embedding_service.domain.value_objects.reranking.result import (
    RerankResult,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as pb,
)


def to_rerank_command(request: pb.RerankRequest) -> RerankDocumentsCommand:
    """Строит команду use case из proto ``RerankRequest``."""
    top_n = request.top_n if request.HasField("top_n") else None
    return RerankDocumentsCommand(
        query=request.query,
        documents=tuple(
            RerankInputDocument(doc.id, doc.text) for doc in request.documents
        ),
        top_n=top_n,
    )


def to_rerank_response(
    request: pb.RerankRequest, result: RerankResult
) -> pb.RerankResponse:
    """Строит proto ``RerankResponse`` из доменного ``RerankResult``.

    Текст документа эхо-транслируется только при ``return_documents=true``;
    ``index`` элемента указывает на исходную позицию во входном запросе.
    """
    include_text = request.return_documents
    ranked: list[pb.RankedDocument] = []
    for item in result.items:
        document = pb.RankedDocument(
            id=item.text_id.value,
            index=item.index,
            score=item.score.value,
        )
        if include_text:
            document.text = request.documents[item.index].text
        ranked.append(document)
    return pb.RerankResponse(results=ranked, model_version=result.model_id.key)
