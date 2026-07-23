"""Contract-тесты плеча embedding (§1, §7).

Держим совместимость с embedding-service в обе стороны:
- наша команда ``requested`` обязана удовлетворять их consumer-схеме;
- их событие ``generated`` (golden sample) обязано проходить наш reader.
Тест краснеет ДО деплоя при рассинхроне контракта.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import validate

from indexing_service.application.embedding_command import build_command_message
from indexing_service.domain.entities.embedding_request import (
    EmbeddingRequest,
    RequestItem,
)
from indexing_service.domain.value_objects.identifiers import JobId, RequestId
from indexing_service.domain.value_objects.job_status import (
    EmbeddingErrorCode,
    RequestStatus,
)
from indexing_service.presentation.messaging.embedding_parsing import (
    parse_embedding_result,
)
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)

pytestmark = pytest.mark.contract

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _ROOT / "contracts" / "embedding"


def _schema(*parts: str) -> dict:
    return json.loads((_CONTRACTS.joinpath(*parts)).read_text(encoding="utf-8"))


def _sample(name: str) -> dict:
    path = _CONTRACTS / "samples" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


_REQUESTED_SCHEMA = _schema("producer", "documents_requested.schema.json")
_GENERATED_SCHEMA = _schema("consumer", "documents_generated.schema.json")
_ENVELOPE_SCHEMA = _schema("envelope.schema.json")


def _request() -> EmbeddingRequest:
    return EmbeddingRequest(
        request_id=RequestId(UUID(int=0xABC)),
        job_id=JobId(UUID(int=1)),
        attempt=0,
        items=(
            RequestItem(text_id="prod-001", text="Товар: наушники"),
            RequestItem(text_id="prod-002", text="Товар: кофемашина"),
        ),
        status=RequestStatus.PENDING,
        next_attempt_at=None,
        created_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
        requested_at=None,
        received_at=None,
    )


def test_built_command_satisfies_embedding_consumer_schema():
    message = build_command_message(
        _request(),
        model="BAAI/bge-m3",
        message_id=UUID(int=0xF00D),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
    )
    validate(instance=message.payload, schema=_REQUESTED_SCHEMA)
    validate(instance=message.payload, schema=_ENVELOPE_SCHEMA)


def test_built_command_without_model_still_valid():
    message = build_command_message(
        _request(),
        model=None,
        message_id=UUID(int=0xF00D),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
    )
    assert "model" not in message.payload["data"]
    validate(instance=message.payload, schema=_REQUESTED_SCHEMA)


def test_requested_sample_matches_producer_schema():
    validate(instance=_sample("documents_requested"), schema=_REQUESTED_SCHEMA)


def test_generated_sample_matches_consumer_schema():
    sample = _sample("documents_generated")
    validate(instance=sample, schema=_GENERATED_SCHEMA)
    validate(instance=sample, schema=_ENVELOPE_SCHEMA)


def test_generated_golden_sample_parses_into_dto():
    envelope = EmbeddingEventEnvelope.model_validate(
        _sample("documents_generated")
    )
    result = parse_embedding_result(envelope)

    assert result.model_version.startswith("BAAI/bge-m3")
    assert result.dim == 1024
    assert len(result.items) == 2

    ok = result.items[0]
    assert ok.is_ok
    assert ok.text_id == "prod-001"
    assert len(ok.dense) == 1024
    assert ok.sparse.indices == (17, 2048, 99000)
    assert ok.token_count == 42

    err = result.items[1]
    assert not err.is_ok
    assert err.error.code is EmbeddingErrorCode.TEXT_TOO_LONG


def test_fake_embedding_service_speaks_the_real_contract():
    """Заглушка для smoke обязана отвечать по настоящей схеме (§12, шаг 7).

    Иначе локальный прогон конвейера «зелёный», а с реальным
    embedding-service всё рассыпается.
    """
    from indexing_service.tools import fake_embedding_service as fake

    request_id = str(UUID(int=7))
    generated = {
        "event_id": str(UUID(int=8)),
        "event_type": "embedding.documents.generated.v1",
        "event_version": "1.0",
        "aggregate_type": "embedding_job",
        "aggregate_id": request_id,
        "occurred_at": "2026-07-24T10:00:00Z",
        "producer": "embedding-service",
        "data": {
            "request_id": request_id,
            "model_version": fake._MODEL_VERSION,
            "dim": fake._DIM,
            "results": [
                fake._result_item({"text_id": "p0", "text": "Кружка"}),
                fake._result_item({"text_id": "p1", "text": "  "}),
            ],
        },
    }

    validate(instance=generated, schema=_GENERATED_SCHEMA)
    validate(instance=generated, schema=_ENVELOPE_SCHEMA)

    result = parse_embedding_result(
        EmbeddingEventEnvelope.model_validate(generated)
    )
    assert result.dim == fake._DIM
    assert len(result.items[0].dense) == fake._DIM
    assert result.items[0].is_ok
    assert not result.items[1].is_ok
    assert result.items[1].error.code is EmbeddingErrorCode.EMPTY_TEXT
