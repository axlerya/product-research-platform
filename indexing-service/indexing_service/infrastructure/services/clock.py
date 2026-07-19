"""Реализация порта ``Clock`` — системное время (UTC)."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает текущий момент в UTC (tz-aware)."""

    def now(self) -> datetime:
        """Текущее время в UTC."""
        return datetime.now(UTC)
