"""Порт ``IdGenerator`` — генератор uuid7 (event_id/корреляция)."""

from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    """Генератор временно-упорядоченных идентификаторов (uuid7)."""

    def new_uuid7(self) -> UUID:
        """Новый uuid7 (event_id результата, корреляция)."""
        ...
