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

    async def count_ready_roots(
        self,
        collection: str,
        *,
        epoch: str,
        expected_model: str | None = None,
    ) -> int:
        """Сколько товаров эпохи реально получили векторы в коллекции (Q6).

        Считаются только корневые точки с водяным знаком модели и версией
        текста: метку эпохи ставит лишь тот путь, который применил результат
        эмбеддинга. Чанки не в счёт — иначе один многочанковый товар
        «закрыл» бы гейт свапа за нескольких.
        """
        ...
