"""Порт ``Clock`` — источник времени (tz-aware UTC)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Возвращает текущий момент (tz-aware UTC)."""

    def now(self) -> datetime:
        """Текущее время."""
        ...
