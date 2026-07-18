"""Системные часы — адаптер порта ``Clock``."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает текущее время в UTC (tz-aware)."""

    def now(self) -> datetime:
        """Текущий момент времени в UTC."""
        return datetime.now(UTC)
