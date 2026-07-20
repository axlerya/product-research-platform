"""Unit-тесты ops-ASGI readiness-хендлера."""

from typing import Any

from embedding_service.presentation.api.ops import readiness_asgi


async def _call(app: Any) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    await app({"type": "http"}, receive, send)
    return sent


async def test_ready_returns_200() -> None:
    sent = await _call(readiness_asgi(lambda: True))
    assert sent[0]["status"] == 200
    assert b"true" in sent[1]["body"]


async def test_not_ready_returns_503() -> None:
    sent = await _call(readiness_asgi(lambda: False))
    assert sent[0]["status"] == 503
    assert b"false" in sent[1]["body"]
