"""Структурное JSON-логирование с contextvars (§10.3).

Сквозной контекст (message_id, request_id, correlation_id, model_version,
trace_id, kind, batch_size, device) заполняется на входном адаптере и
автоматически подмешивается в каждую строку.
"""

import json
import logging
from contextvars import ContextVar
from typing import Any

_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "log_context", default=None
)


def bind_context(**fields: Any) -> None:
    """Добавляет непустые поля в контекст логирования."""
    current = dict(_CONTEXT.get() or {})
    current.update({k: v for k, v in fields.items() if v is not None})
    _CONTEXT.set(current)


def clear_context() -> None:
    """Сбрасывает контекст (в конце обработки сообщения/запроса)."""
    _CONTEXT.set(None)


class JsonFormatter(logging.Formatter):
    """Форматтер JSON: подмешивает contextvars-контекст в каждую строку."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_CONTEXT.get() or {})
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Настраивает root-логгер на JSON-вывод."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
