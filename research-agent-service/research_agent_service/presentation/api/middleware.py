"""Pure-ASGI middleware: контекст запроса в логах (trace_id/путь/…).

Чистое ASGI-middleware (не BaseHTTPMiddleware) выполняет приложение в той же
задаче, поэтому связанный contextvars-контекст виден и в обработчике, и в
use case: все JSON-логи запроса несут эти поля. Контекст очищается после
ответа.
"""

import logging

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from research_agent_service.infrastructure.observability.logging import (
    bind_context,
    clear_context,
)

_logger = logging.getLogger("research_agent_service.request")


class RequestContextMiddleware:
    """Связывает контекст запроса и пишет строку доступа в лог."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        context = {"method": scope["method"], "path": scope["path"]}
        trace_id = headers.get("x-trace-id")
        if trace_id is not None:
            context["trace_id"] = trace_id
        correlation_id = headers.get("x-correlation-id")
        if correlation_id is not None:
            context["correlation_id"] = correlation_id
        bind_context(**context)

        status = {"code": 0}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, _send)
            bind_context(status=str(status["code"]))
            _logger.info("request handled")
        finally:
            clear_context()


def install_request_context(app: FastAPI) -> None:
    """Подключает middleware контекста запроса."""
    app.add_middleware(RequestContextMiddleware)
