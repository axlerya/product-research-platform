"""Тесты мелких инфраструктурных сервисов."""

from indexing_service.infrastructure.services.clock import SystemClock


def test_now_is_utc_aware():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0
