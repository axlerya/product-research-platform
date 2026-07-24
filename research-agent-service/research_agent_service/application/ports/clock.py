"""Порт Clock — источник tz-aware времени (детерминизм в тестах)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Часы: текущий момент в UTC (tz-aware)."""

    def now(self) -> datetime:
        """Возвращает текущий момент (tz-aware, UTC)."""
        ...
