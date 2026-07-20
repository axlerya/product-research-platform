"""Unit-тесты messaging: схемы, parsing, топология, сериализация, dispatch."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from embedding_service.application.dto import (
    DocumentsGenerated,
    EmbedDocumentsCommand,
    RawTextItem,
)
from embedding_service.application.exceptions import (
    InferenceError,
    ValidationError,
)
from embedding_service.application.use_cases.embed_documents import (
    EmbedDocuments,
)
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.infrastructure.embedding.deterministic import (
    DeterministicEmbeddingProvider,
)
from embedding_service.presentation.messaging import topology
from embedding_service.presentation.messaging.error_policy import dispatch
from embedding_service.presentation.messaging.parsing import to_command
from embedding_service.presentation.messaging.schemas import (
    RequestedData,
    RequestedEnvelope,
    RequestedItem,
)
from embedding_service.presentation.messaging.serialization import (
    to_generated_envelope,
)

_REQ_ID = "0192f0c8-0000-7000-8000-000000000abc"
_EVT_ID = UUID("0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a")
_NOW = datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC)

_PRODUCER_SCHEMA = json.loads(
    (
        Path(__file__).parents[3]
        / "contracts"
        / "rabbitmq"
        / "producer"
        / "documents_generated"
        / "1.0.json"
    ).read_text(encoding="utf-8")
)

VALID_PAYLOAD: dict[str, Any] = {
    "event_id": str(_EVT_ID),
    "event_type": topology.REQUESTED_RK,
    "event_version": "1.0",
    "aggregate_type": "embedding_job",
    "occurred_at": "2026-07-20T10:15:30.123456Z",
    "producer": "read-model-builder",
    "trace_id": "trace-xyz",
    "data": {
        "request_id": _REQ_ID,
        "return_dense": True,
        "return_sparse": True,
        "items": [{"text_id": "p1", "text": "hello"}],
    },
}


def _envelope(**data_overrides: Any) -> RequestedEnvelope:
    data = {
        "request_id": _REQ_ID,
        "return_dense": True,
        "return_sparse": True,
        "items": [RequestedItem(text_id="p1", text="hello")],
    }
    data.update(data_overrides)
    return RequestedEnvelope(
        event_id=_EVT_ID,
        event_type=topology.REQUESTED_RK,
        occurred_at=_NOW,
        producer="read-model-builder",
        trace_id="trace-xyz",
        data=RequestedData(**data),
    )


class TestSchemas:
    def test_parses_valid(self) -> None:
        env = RequestedEnvelope.model_validate(VALID_PAYLOAD)
        assert env.data.request_id == UUID(_REQ_ID)
        assert env.data.items[0].text == "hello"

    def test_tolerant_to_unknown_field(self) -> None:
        payload = {**VALID_PAYLOAD, "future": 1}
        RequestedEnvelope.model_validate(payload)

    def test_empty_items_rejected(self) -> None:
        payload = {
            **VALID_PAYLOAD,
            "data": {**VALID_PAYLOAD["data"], "items": []},
        }
        # pydantic ValidationError — подкласс ValueError
        with pytest.raises(ValueError):
            RequestedEnvelope.model_validate(payload)


class TestParsing:
    def test_to_command(self) -> None:
        command = to_command(_envelope())
        assert isinstance(command, EmbedDocumentsCommand)
        assert command.request_id == _REQ_ID
        assert command.items == (RawTextItem(text_id="p1", text="hello"),)
        assert command.return_dense is True


class TestTopology:
    def test_main_queue_args(self) -> None:
        queue = topology.main_queue()
        assert queue.name == topology.MAIN_QUEUE_NAME
        assert queue.arguments["x-queue-type"] == "quorum"
        assert (
            queue.arguments["x-dead-letter-exchange"]
            == topology.RETRY_EXCHANGE.name
        )

    def test_retry_queue_ttl(self) -> None:
        queue = topology.retry_queue(30_000)
        assert queue.arguments["x-message-ttl"] == 30_000
        assert (
            queue.arguments["x-dead-letter-exchange"]
            == topology.REQUEUE_EXCHANGE.name
        )

    def test_parking_queue(self) -> None:
        assert topology.parking_queue().name == topology.PARKING_QUEUE_NAME


class TestSerialization:
    def test_ok_and_error_structure(self) -> None:
        provider = DeterministicEmbeddingProvider(model_id=_mid())
        result = DocumentsGenerated(
            request_id=_REQ_ID,
            model_key=_mid().key,
            dim=4,
            results=(),
        )
        # пустой результат — проверяем каркас конверта
        wire = to_generated_envelope(
            _envelope(), result, event_id=_EVT_ID, occurred_at=_NOW
        )
        assert wire["producer"] == "embedding-service"
        assert wire["event_type"] == topology.GENERATED_RK
        assert wire["trace_id"] == "trace-xyz"
        assert wire["data"]["model_version"] == _mid().key
        assert wire["occurred_at"].endswith("Z")
        assert provider.model_id == _mid()

    def test_dense_omitted_when_not_requested(self) -> None:
        from embedding_service.domain.value_objects.dense_vector import (
            DenseVector,
        )
        from embedding_service.domain.value_objects.embedding import Embedding
        from embedding_service.domain.value_objects.item_result import (
            EmbeddingItemResult,
        )
        from embedding_service.domain.value_objects.sparse_vector import (
            SparseVector,
        )
        from embedding_service.domain.value_objects.text_id import TextId
        from embedding_service.domain.value_objects.token_count import (
            TokenCount,
        )

        emb = Embedding(
            DenseVector((0.1, 0.2)),
            SparseVector((1,), (0.5,)),
            _mid(dim=2),
        )
        result = DocumentsGenerated(
            request_id=_REQ_ID,
            model_key=_mid(dim=2).key,
            dim=2,
            results=(EmbeddingItemResult.ok(TextId("p1"), emb, TokenCount(3)),),
        )
        wire = to_generated_envelope(
            _envelope(return_dense=False, return_sparse=True),
            result,
            event_id=_EVT_ID,
            occurred_at=_NOW,
        )
        item = wire["data"]["results"][0]
        assert "dense" not in item
        assert "sparse" in item

    async def test_matches_producer_schema(self) -> None:
        provider = DeterministicEmbeddingProvider(model_id=_mid(1024))
        limits = EmbeddingLimits(
            max_texts=10,
            max_text_chars=1000,
            max_tokens=8192,
            max_total_bytes=100_000,
        )
        uc = EmbedDocuments(provider, limits)
        command = EmbedDocumentsCommand(
            request_id=_REQ_ID,
            items=(
                RawTextItem(text_id="p1", text="товар"),
                RawTextItem(text_id="p2", text="   "),
            ),
            return_dense=True,
            return_sparse=True,
        )
        result = await uc.handle(command)  # p2 пустой → error, p1 ok
        request = _envelope(
            items=[
                RequestedItem(text_id="p1", text="товар"),
                RequestedItem(text_id="p2", text=" "),
            ]
        )
        wire = to_generated_envelope(
            request, result, event_id=_EVT_ID, occurred_at=_NOW
        )
        Draft202012Validator(_PRODUCER_SCHEMA).validate(wire)
        statuses = [r["status"] for r in wire["data"]["results"]]
        assert statuses == ["ok", "error"]

    def test_correlation_included_trace_omitted(self) -> None:
        envelope = RequestedEnvelope(
            event_id=_EVT_ID,
            event_type=topology.REQUESTED_RK,
            occurred_at=_NOW,
            producer="read-model-builder",
            trace_id=None,
            correlation_id="corr-1",
            data=RequestedData(
                request_id=_REQ_ID,
                return_dense=True,
                return_sparse=True,
                items=[RequestedItem(text_id="p1", text="hi")],
            ),
        )
        result = DocumentsGenerated(
            request_id=_REQ_ID, model_key="k", dim=4, results=()
        )
        wire = to_generated_envelope(
            envelope, result, event_id=_EVT_ID, occurred_at=_NOW
        )
        assert "trace_id" not in wire
        assert wire["correlation_id"] == "corr-1"

    def test_sparse_omitted_when_not_requested(self) -> None:
        from embedding_service.domain.value_objects.dense_vector import (
            DenseVector,
        )
        from embedding_service.domain.value_objects.embedding import Embedding
        from embedding_service.domain.value_objects.item_result import (
            EmbeddingItemResult,
        )
        from embedding_service.domain.value_objects.sparse_vector import (
            SparseVector,
        )
        from embedding_service.domain.value_objects.text_id import TextId
        from embedding_service.domain.value_objects.token_count import (
            TokenCount,
        )

        emb = Embedding(
            DenseVector((0.1, 0.2)), SparseVector((1,), (0.5,)), _mid(dim=2)
        )
        result = DocumentsGenerated(
            request_id=_REQ_ID,
            model_key=_mid(dim=2).key,
            dim=2,
            results=(EmbeddingItemResult.ok(TextId("p1"), emb, TokenCount(3)),),
        )
        wire = to_generated_envelope(
            _envelope(return_dense=True, return_sparse=False),
            result,
            event_id=_EVT_ID,
            occurred_at=_NOW,
        )
        item = wire["data"]["results"][0]
        assert "dense" in item
        assert "sparse" not in item


def _mid(dim: int = 4) -> EmbeddingModelId:
    return EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=dim,
    )


def _fakes(
    log: list[str],
    *,
    headers: dict[str, Any] | None = None,
    result: DocumentsGenerated | None = None,
    error: Exception | None = None,
):
    class _Msg:
        def __init__(self) -> None:
            self.headers = headers or {}

        async def ack(self) -> None:
            log.append("ack")

        async def reject(self, requeue: bool = False) -> None:
            log.append(f"reject:{requeue}")

    class _UseCase:
        async def handle(self, command: Any) -> DocumentsGenerated:
            log.append("handle")
            if error is not None:
                raise error
            assert result is not None
            return result

    async def _publish(envelope: Any, res: Any) -> None:
        log.append("publish")

    async def _park(message: Any) -> None:
        log.append("park")

    return _Msg(), _UseCase(), _publish, _park


_OK_RESULT = DocumentsGenerated(
    request_id=_REQ_ID, model_key="k", dim=1024, results=()
)


class TestDispatch:
    async def test_happy_ack_after_confirm(self) -> None:
        log: list[str] = []
        msg, uc, publish, park = _fakes(log, result=_OK_RESULT)
        await dispatch(
            VALID_PAYLOAD,
            msg,
            use_case=uc,
            publish=publish,
            park=park,
            max_attempts=5,
        )
        assert log == ["handle", "publish", "ack"]  # ack строго после publish

    async def test_bad_schema_parked(self) -> None:
        log: list[str] = []
        payload = {
            **VALID_PAYLOAD,
            "data": {**VALID_PAYLOAD["data"], "items": []},
        }
        msg, uc, publish, park = _fakes(log, result=_OK_RESULT)
        await dispatch(
            payload,
            msg,
            use_case=uc,
            publish=publish,
            park=park,
            max_attempts=5,
        )
        assert log == ["park", "ack"]  # handle не вызывался

    async def test_permanent_error_parked(self) -> None:
        log: list[str] = []
        msg, uc, publish, park = _fakes(
            log, error=ValidationError("битый батч")
        )
        await dispatch(
            VALID_PAYLOAD,
            msg,
            use_case=uc,
            publish=publish,
            park=park,
            max_attempts=5,
        )
        assert log == ["handle", "park", "ack"]  # publish не вызывался

    async def test_transient_rejected_for_retry(self) -> None:
        log: list[str] = []
        msg, uc, publish, park = _fakes(log, error=InferenceError("oom"))
        await dispatch(
            VALID_PAYLOAD,
            msg,
            use_case=uc,
            publish=publish,
            park=park,
            max_attempts=5,
        )
        assert log == ["handle", "reject:False"]

    async def test_transient_parked_after_max_attempts(self) -> None:
        log: list[str] = []
        headers = {"x-death": [{"count": 5}]}
        msg, uc, publish, park = _fakes(
            log, headers=headers, error=InferenceError("oom")
        )
        await dispatch(
            VALID_PAYLOAD,
            msg,
            use_case=uc,
            publish=publish,
            park=park,
            max_attempts=5,
        )
        assert log == ["handle", "park", "ack"]
