"""Тесты JSON-логирования."""

import json
import logging
import sys

from research_agent_service.infrastructure.observability.logging import (
    JsonFormatter,
    bind_context,
    clear_context,
    configure_logging,
)


def _record(msg: str, exc: object = None) -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, msg, None, exc)


def test_formatter_outputs_json() -> None:
    """Запись сериализуется в JSON с level и message."""
    clear_context()

    payload = json.loads(JsonFormatter().format(_record("привет")))

    assert payload["level"] == "INFO"
    assert payload["message"] == "привет"


def test_context_fields_appear_in_output() -> None:
    """Поля контекста попадают в запись."""
    clear_context()
    bind_context(agent_run_id="run-1")

    payload = json.loads(JsonFormatter().format(_record("x")))

    assert payload["agent_run_id"] == "run-1"
    clear_context()


def test_clear_context_removes_fields() -> None:
    """clear_context убирает ранее связанные поля."""
    bind_context(k="v")
    clear_context()

    payload = json.loads(JsonFormatter().format(_record("x")))

    assert "k" not in payload


def test_exception_is_serialized() -> None:
    """Трассировка исключения попадает в поле exc."""
    clear_context()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "t", logging.ERROR, __file__, 1, "err", None, sys.exc_info()
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "boom" in payload["exc"]


def test_configure_logging_sets_json_handler() -> None:
    """configure_logging ставит JSON-хендлер и уровень."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        configure_logging("DEBUG")
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.DEBUG
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
