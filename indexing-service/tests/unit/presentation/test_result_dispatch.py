"""Тесты политики ack/retry/DLQ консюмера результатов (§7.4)."""

from indexing_service.application.exceptions import VectorIndexError
from indexing_service.presentation.messaging.embedding_schemas import (
    EmbeddingEventEnvelope,
)
from indexing_service.presentation.messaging.result_dispatch import (
    dispatch_result,
)

_REQUEST_ID = "0192f0c8-0000-7000-8000-000000000abc"


def _envelope(
    *, event_type="embedding.documents.generated.v1"
) -> EmbeddingEventEnvelope:
    return EmbeddingEventEnvelope.model_validate(
        {
            "event_id": "0192f0c8-9999-7abc-8def-1a2b3c4d5e6f",
            "event_type": event_type,
            "aggregate_id": _REQUEST_ID,
            "occurred_at": "2026-07-20T10:15:31.456789Z",
            "data": {
                "request_id": _REQUEST_ID,
                "model_version": "m",
                "dim": 3,
                "results": [{"text_id": "c0", "status": "ok"}],
            },
        }
    )


class _FakeMessage:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.acked = False
        self.rejected = False

    async def ack(self):
        self.acked = True

    async def reject(self, requeue: bool = False):
        self.rejected = True


class _FakeUseCase:
    def __init__(self, error=None):
        self._error = error
        self.calls = 0

    async def handle(self, result):
        self.calls += 1
        if self._error is not None:
            raise self._error


class _Parker:
    def __init__(self):
        self.parked = []

    async def __call__(self, message):
        self.parked.append(message)


async def test_success_acks():
    message, parker = _FakeMessage(), _Parker()
    use_case = _FakeUseCase()
    await dispatch_result(
        _envelope(), message, use_case=use_case, park=parker, max_attempts=5
    )
    assert use_case.calls == 1
    assert message.acked
    assert parker.parked == []


async def test_poison_event_type_parks_and_acks():
    message, parker = _FakeMessage(), _Parker()
    await dispatch_result(
        _envelope(event_type="embedding.wrong.v1"),
        message,
        use_case=_FakeUseCase(),
        park=parker,
        max_attempts=5,
    )
    assert parker.parked == [message]
    assert message.acked


async def test_transient_error_rejects_into_retry():
    message, parker = _FakeMessage(), _Parker()
    await dispatch_result(
        _envelope(),
        message,
        use_case=_FakeUseCase(VectorIndexError("qdrant down")),
        park=parker,
        max_attempts=5,
    )
    assert message.rejected
    assert not message.acked
    assert parker.parked == []


async def test_transient_error_parks_when_attempts_exhausted():
    message = _FakeMessage(headers={"x-death": [{"count": 5}]})
    parker = _Parker()
    await dispatch_result(
        _envelope(),
        message,
        use_case=_FakeUseCase(VectorIndexError("qdrant down")),
        park=parker,
        max_attempts=5,
    )
    assert parker.parked == [message]
    assert message.acked
