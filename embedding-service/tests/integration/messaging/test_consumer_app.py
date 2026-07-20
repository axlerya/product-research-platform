"""Integration: FastStream consumer end-to-end через TestRabbitBroker (§11.4).

Команда → subscriber → dispatch → BGE-M3(FAKE) → публикация generated.
"""

import pytest
from faststream.rabbit import RabbitQueue, TestRabbitBroker

from embedding_service.bootstrap import build_deps
from embedding_service.infrastructure.config import Settings
from embedding_service.presentation.messaging.consumer_app import (
    build_consumer,
)
from embedding_service.presentation.messaging.topology import (
    EVENTS_EXCHANGE,
    GENERATED_RK,
    JOBS_EXCHANGE,
    REQUESTED_RK,
)

pytestmark = pytest.mark.integration

_COMMAND = {
    "event_id": "0192f0c8-7b3a-7e2d-9a1c-1f2e3d4c5b6a",
    "event_type": REQUESTED_RK,
    "event_version": "1.0",
    "aggregate_type": "embedding_job",
    "occurred_at": "2026-07-20T10:15:30.123456Z",
    "producer": "read-model-builder",
    "trace_id": "trace-xyz",
    "data": {
        "request_id": "0192f0c8-0000-7000-8000-000000000abc",
        "return_dense": True,
        "return_sparse": True,
        "items": [
            {"text_id": "p1", "text": "товар"},
            {"text_id": "p2", "text": "   "},
        ],
    },
}


async def test_consumer_publishes_generated() -> None:
    settings = Settings(_env_file=None, provider_mode="deterministic", dim=8)
    deps = build_deps(settings)
    app = build_consumer(deps, lambda: True)
    broker = app.broker
    captured: list[dict] = []

    @broker.subscriber(
        RabbitQueue("test.spy", routing_key=GENERATED_RK), EVENTS_EXCHANGE
    )
    async def _spy(body: dict) -> None:
        captured.append(body)

    try:
        async with TestRabbitBroker(broker):
            await broker.publish(
                _COMMAND,
                exchange=JOBS_EXCHANGE,
                routing_key=REQUESTED_RK,
            )
    finally:
        await deps.aclose()

    assert captured, "событие generated не опубликовано"
    event = captured[0]
    assert event["event_type"] == GENERATED_RK
    assert event["producer"] == "embedding-service"
    assert event["data"]["dim"] == 8
    statuses = [r["status"] for r in event["data"]["results"]]
    assert statuses == ["ok", "error"]  # p1 ok, p2 пустой → error
