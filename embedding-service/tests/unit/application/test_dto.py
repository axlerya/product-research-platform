"""Unit-тесты DTO слоя application (frozen dataclass, не Pydantic)."""

import dataclasses

from embedding_service.application.dto import (
    DocumentsGenerated,
    EmbedDocumentsCommand,
    EmbedQueriesQuery,
    EmbedQueryQuery,
    ProviderStatus,
    RawTextItem,
)
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
    ItemError,
)
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.text_id import TextId


def test_provider_status() -> None:
    status = ProviderStatus(
        loaded=True,
        device="cuda:0",
        precision="fp16",
        degraded=False,
        model_key="BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024",
    )
    assert status.loaded
    assert dataclasses.is_dataclass(status)


def test_embed_documents_command() -> None:
    cmd = EmbedDocumentsCommand(
        request_id="req-1",
        items=(RawTextItem(text_id="p-1", text="hi"),),
        return_dense=True,
        return_sparse=True,
    )
    assert cmd.request_id == "req-1"
    assert cmd.items[0].text == "hi"


def test_query_dtos() -> None:
    q1 = EmbedQueryQuery(text="hello", request_id=None)
    q2 = EmbedQueriesQuery(texts=("a", "b"), request_id="r")
    assert q1.request_id is None
    assert q2.texts == ("a", "b")


def test_documents_generated() -> None:
    gen = DocumentsGenerated(
        request_id="req-1",
        model_key="BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024",
        dim=1024,
        results=(),
    )
    assert gen.dim == 1024
    assert isinstance(gen.results, tuple)


def test_dtos_are_frozen() -> None:
    q = EmbedQueryQuery(text="x", request_id=None)
    try:
        q.text = "y"  # type: ignore[misc]
    except (dataclasses.FrozenInstanceError, AttributeError):
        return
    raise AssertionError("DTO должен быть frozen")


def test_documents_generated_results_type() -> None:
    result = EmbeddingItemResult.failed(
        TextId("x"),
        error=ItemError(EmbeddingErrorCode.EMPTY_TEXT, "x"),
    )
    gen = DocumentsGenerated(
        request_id="r", model_key="k", dim=1024, results=(result,)
    )
    assert gen.results[0].text_id.value == "x"
