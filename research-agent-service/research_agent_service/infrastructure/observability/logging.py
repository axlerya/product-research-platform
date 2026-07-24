"""JSON-логирование с контекстными полями (contextvars)."""

import json
import logging
from contextvars import ContextVar

_context: ContextVar[dict[str, str] | None] = ContextVar(
    "log_context", default=None
)


def _current() -> dict[str, str]:
    return _context.get() or {}


def bind_context(**fields: str) -> None:
    """Добавляет поля контекста ко всем последующим записям."""
    _context.set({**_current(), **fields})


def clear_context() -> None:
    """Сбрасывает контекст (в конце запроса/обработки)."""
    _context.set(None)


class JsonFormatter(logging.Formatter):
    """Форматтер: одна запись — одна JSON-строка с контекстом."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_current(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Настраивает корневой логгер на JSON-вывод."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
