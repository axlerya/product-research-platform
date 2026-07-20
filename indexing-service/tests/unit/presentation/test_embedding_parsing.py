"""Тесты tolerant-разбора события ``embedding.documents.generated.v1``."""

from uuid import UUID

import pytest

from indexing_service.application.exceptions import EventValidationError
from indexing_service.domain.value_objects.job_status import EmbeddingErrorCode
from indexing_service.presentation.messaging.embedding_parsing import (
    parse_embedding_result,
)
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)

_REQUEST_ID = "0192f0c8-0000-7000-8000-000000000abc"


def _envelope(data: dict, event_type: str = "embedding.documents.generated.v1"):
    return EmbeddingEventEnvelope.model_validate(
        {
            "event_id": "0192f0c8-9999-7abc-8def-1a2b3c4d5e6f",
            "event_type": event_type,
            "aggregate_id": _REQUEST_ID,
            "occurred_at": "2026-07-20T10:15:31.456789Z",
            "data": data,
        }
    )


def _data(results: list[dict]) -> dict:
    return {
        "request_id": _REQUEST_ID,
        "model_version": "BAAI/bge-m3@x|dim=1024",
        "dim": 1024,
        "results": results,
    }


def test_parses_ok_and_error_items_in_order():
    result = parse_embedding_result(
        _envelope(
            _data(
                [
                    {
                        "text_id": "p1",
                        "status": "ok",
                        "dense": [0.1, 0.2, 0.3],
                        "sparse": {"indices": [17, 2048], "values": [0.3, 0.7]},
                        "token_count": 42,
                    },
                    {
                        "text_id": "p2",
                        "status": "error",
                        "error": {
                            "code": "TEXT_TOO_LONG",
                            "message": "слишком длинный",
                        },
                    },
                ]
            )
        )
    )

    assert result.request_id == UUID(_REQUEST_ID)
    assert result.dim == 1024
    assert len(result.items) == 2

    ok = result.items[0]
    assert ok.is_ok
    assert ok.dense == (0.1, 0.2, 0.3)
    assert ok.sparse.indices == (17, 2048)
    assert ok.sparse.values == (0.3, 0.7)
    assert ok.token_count == 42

    err = result.items[1]
    assert not err.is_ok
    assert err.error.code is EmbeddingErrorCode.TEXT_TOO_LONG
    assert err.error.message == "слишком длинный"
    assert err.dense is None


def test_ok_item_without_dense_sparse_token():
    result = parse_embedding_result(
        _envelope(_data([{"text_id": "p1", "status": "ok"}]))
    )
    item = result.items[0]
    assert item.dense is None
    assert item.sparse is None
    assert item.token_count is None
    assert item.is_ok


def test_rejects_unknown_event_type():
    with pytest.raises(EventValidationError):
        parse_embedding_result(
            _envelope(_data([]), event_type="embedding.something.else.v1")
        )


def test_rejects_unknown_error_code():
    with pytest.raises(EventValidationError):
        parse_embedding_result(
            _envelope(
                _data(
                    [
                        {
                            "text_id": "p1",
                            "status": "error",
                            "error": {"code": "WAT", "message": "?"},
                        }
                    ]
                )
            )
        )


def test_rejects_unknown_status():
    with pytest.raises(EventValidationError):
        parse_embedding_result(
            _envelope(_data([{"text_id": "p1", "status": "skipped"}]))
        )


def test_tolerant_to_extra_fields():
    data = _data([{"text_id": "p1", "status": "ok", "unknown": 1}])
    data["extra_top"] = "ignored"
    result = parse_embedding_result(_envelope(data))
    assert result.items[0].text_id == "p1"
