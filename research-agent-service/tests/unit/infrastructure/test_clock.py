"""Тесты SystemClock."""

from research_agent_service.infrastructure.services.clock import SystemClock


def test_now_is_utc_aware() -> None:
    """now() возвращает tz-aware момент с нулевым смещением (UTC)."""
    now = SystemClock().now()

    assert now.tzinfo is not None
    offset = now.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0
