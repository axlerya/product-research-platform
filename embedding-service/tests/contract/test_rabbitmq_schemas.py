"""Contract-тесты RabbitMQ-схем и кросс-сервисных инвариантов (§11.3).

Валидирует golden-примеры против JSON Schema (consumer tolerant / producer
strict) и проверяет пины, на которые завязан потребитель read-model.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.sparse_vector import SparseVector

pytestmark = pytest.mark.contract

_CONTRACTS = Path(__file__).parents[2] / "contracts" / "rabbitmq"


def _load(rel: str) -> dict:
    return json.loads((_CONTRACTS / rel).read_text(encoding="utf-8"))


CONSUMER_SCHEMA = _load("consumer/documents_requested/1.0.json")
PRODUCER_SCHEMA = _load("producer/documents_generated/1.0.json")
ENVELOPE_SCHEMA = _load("envelope/1.0.json")
REQUESTED = _load("samples/documents_requested.json")
GENERATED = _load("samples/documents_generated.json")


def test_schemas_pass_metaschema() -> None:
    for schema in (CONSUMER_SCHEMA, PRODUCER_SCHEMA, ENVELOPE_SCHEMA):
        Draft202012Validator.check_schema(schema)


def test_requested_sample_valid() -> None:
    Draft202012Validator(CONSUMER_SCHEMA).validate(REQUESTED)


def test_generated_sample_valid() -> None:
    Draft202012Validator(PRODUCER_SCHEMA).validate(GENERATED)


def test_both_samples_match_envelope() -> None:
    validator = Draft202012Validator(ENVELOPE_SCHEMA)
    validator.validate(REQUESTED)
    validator.validate(GENERATED)


def test_consumer_tolerant_to_unknown_field() -> None:
    # MINOR-эволюция продюсера: незнакомое поле не ломает чтение.
    doc = {**REQUESTED, "future_field": "ignored"}
    doc["data"] = {**doc["data"], "future_flag": True}
    Draft202012Validator(CONSUMER_SCHEMA).validate(doc)


def test_producer_strict_rejects_unknown_field() -> None:
    doc = {**GENERATED, "future_field": "nope"}
    with pytest.raises(ValidationError):
        Draft202012Validator(PRODUCER_SCHEMA).validate(doc)


def test_model_version_matches_domain_key() -> None:
    expected = EmbeddingModelId(
        name="BAAI/bge-m3",
        revision="unknown",
        pooling="cls",
        normalized=True,
        dim=1024,
    ).key
    assert GENERATED["data"]["model_version"] == expected


def test_dense_length_equals_dim() -> None:
    dim = GENERATED["data"]["dim"]
    assert dim == 1024
    for result in GENERATED["data"]["results"]:
        if result["status"] == "ok":
            assert len(result["dense"]) == dim


def test_sparse_is_canonical() -> None:
    for result in GENERATED["data"]["results"]:
        if result["status"] == "ok":
            sparse = SparseVector(
                tuple(result["sparse"]["indices"]),
                tuple(result["sparse"]["values"]),
            )
            assert list(sparse.indices) == sorted(set(sparse.indices))


def test_results_order_matches_command_items() -> None:
    request_ids = [item["text_id"] for item in REQUESTED["data"]["items"]]
    result_ids = [r["text_id"] for r in GENERATED["data"]["results"]]
    assert request_ids == result_ids
