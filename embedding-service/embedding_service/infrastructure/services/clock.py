"""Реализация порта ``Clock`` — системные часы (tz-aware UTC)."""

from datetime import UTC, datetime


class SystemClock:
    """Системные часы: ``now()`` → tz-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
