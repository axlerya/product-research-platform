"""Порт IdGenerator — генерация uuidv7 (для outbox/событий)."""

from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    """Источник монотонных идентификаторов uuidv7."""

    def new_uuid7(self) -> UUID:
        """Возвращает новый UUID версии 7."""
        ...
