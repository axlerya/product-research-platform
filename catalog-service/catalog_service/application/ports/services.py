"""Вспомогательные порты детерминизма: часы и генератор идентификаторов."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from catalog_service.domain.value_objects.identifiers import ProductId


class Clock(Protocol):
    """Источник текущего времени (tz-aware UTC)."""

    def now(self) -> datetime:
        """Возвращает текущий момент времени."""
        ...


class IdGenerator(Protocol):
    """Генератор идентификаторов (uuidv7)."""

    def new_product_id(self) -> ProductId:
        """Возвращает новый идентификатор товара."""
        ...

    def new_message_id(self) -> UUID:
        """Возвращает новый message-id для строки outbox."""
        ...
