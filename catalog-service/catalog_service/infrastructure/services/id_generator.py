"""Генератор идентификаторов uuidv7 — адаптер порта ``IdGenerator``."""

from uuid import UUID

from catalog_service.domain.value_objects.identifiers import ProductId


class Uuid7Generator:
    """Выдаёт временно-упорядоченные идентификаторы uuidv7."""

    def new_product_id(self) -> ProductId:
        """Новый идентификатор товара."""
        return ProductId.new()

    def new_message_id(self) -> UUID:
        """Новый message-id (uuidv7) для строки outbox."""
        return ProductId.new().value
