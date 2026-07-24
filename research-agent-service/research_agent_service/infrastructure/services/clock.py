"""SystemClock — реальные часы UTC (реализация порта Clock)."""

from datetime import UTC, datetime


class SystemClock:
    """Часы на системном времени в UTC (tz-aware)."""

    def now(self) -> datetime:
        """Возвращает текущий момент в UTC."""
        return datetime.now(UTC)
