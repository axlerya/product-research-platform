"""Порт ``VectorIndexAdmin`` — управление коллекциями и алиасом (§8)."""

from typing import Protocol

from indexing_service.application.ports.vector_index import VectorIndex


class VectorIndexAdmin(Protocol):
    """Провижининг коллекций и переключение алиаса (blue-green, §8.2)."""

    async def provision(self, collection: str) -> None:
        """Idempotent: создаёт коллекцию с payload-индексами."""
        ...

    async def swap_alias(self, alias: str, to_collection: str) -> None:
        """Атомарно направляет ``alias`` на ``to_collection``."""
        ...

    def writer(self, collection: str) -> VectorIndex:
        """Возвращает ``VectorIndex``, пишущий в указанную коллекцию."""
        ...
