"""Тесты middleware контекста запроса (чистое ASGI, детерминированно).

Обработчик-проба читает связанный контекст и возвращает его — так поведение
middleware проверяется без зависимости от глобального состояния logging.
"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from research_agent_service.infrastructure.observability.logging import (
    _current,
    clear_context,
)
from research_agent_service.presentation.api.middleware import (
    RequestContextMiddleware,
    install_request_context,
)


def _probe_app() -> FastAPI:
    app = FastAPI()
    install_request_context(app)

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return dict(_current())

    return app


async def _probe(headers: dict[str, str]) -> dict:
    clear_context()
    transport = ASGITransport(app=_probe_app())
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        response = await client.get("/probe", headers=headers)
    return response.json()


async def test_middleware_binds_trace_path_and_correlation() -> None:
    """Заголовки и путь связываются в контекст, видимый в обработчике."""
    body = await _probe({"X-Trace-Id": "tx", "X-Correlation-Id": "cx"})

    assert body["method"] == "GET"
    assert body["path"] == "/probe"
    assert body["trace_id"] == "tx"
    assert body["correlation_id"] == "cx"


async def test_middleware_without_headers() -> None:
    """Без заголовков — только метод и путь, без trace_id/correlation_id."""
    body = await _probe({})

    assert body["path"] == "/probe"
    assert "trace_id" not in body
    assert "correlation_id" not in body


async def test_non_http_scope_is_passed_through() -> None:
    """Не-http scope (например lifespan) проходит без связывания контекста."""
    seen: list[str] = []

    async def _inner(scope: dict, receive: object, send: object) -> None:
        seen.append(scope["type"])

    middleware = RequestContextMiddleware(_inner)
    await middleware({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]
