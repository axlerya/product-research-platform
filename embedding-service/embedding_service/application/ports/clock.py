"""Порт ``Clock`` — источник времени (tz-aware UTC)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Часы: ``now()`` возвращает tz-aware UTC-время."""

    def now(self) -> datetime:
        """Текущий момент (tz-aware UTC)."""
        ...
