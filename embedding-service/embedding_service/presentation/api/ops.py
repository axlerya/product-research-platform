"""ops-ASGI readiness-хендлер (§10.4): ``/ready`` → 200/503 по готовности.

REST для эмбеддингов НЕ выдаётся — только health/диагностика.
"""

from collections.abc import Awaitable, Callable
from typing import Any

_Scope = dict[str, Any]
_Receive = Callable[[], Awaitable[dict[str, Any]]]
_Send = Callable[[dict[str, Any]], Awaitable[None]]
_AsgiApp = Callable[[_Scope, _Receive, _Send], Awaitable[None]]


def readiness_asgi(is_ready: Callable[[], bool]) -> _AsgiApp:
    """ASGI-приложение ``/ready``: 200 при готовности, иначе 503."""

    async def app(scope: _Scope, receive: _Receive, send: _Send) -> None:
        ready = is_ready()
        status = 200 if ready else 503
        body = b'{"ready":true}' if ready else b'{"ready":false}'
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app
