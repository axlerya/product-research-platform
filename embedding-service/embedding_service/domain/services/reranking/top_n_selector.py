"""Доменный сервис ``TopNSelector`` — упорядочивание и отсечение top_n."""

from collections.abc import Sequence

from embedding_service.domain.value_objects.reranking.ranked_item import (
    RankedItem,
)
from embedding_service.domain.value_objects.reranking.top_n import TopN


class TopNSelector:
    """Сортирует элементы по убыванию скора и отсекает top_n.

    Сортировка детерминирована: при равных скорах порядок задаётся исходной
    позицией (``index``) по возрастанию — стабильный, воспроизводимый вывод.
    """

    @staticmethod
    def select(
        items: Sequence[RankedItem], top_n: TopN | None
    ) -> tuple[RankedItem, ...]:
        """Возвращает элементы по убыванию скора, усечённые до ``top_n``.

        Args:
            items: Оценённые элементы (в произвольном порядке).
            top_n: Ограничение выдачи; ``None`` — вернуть все.

        Returns:
            Кортеж элементов по убыванию скора (при равенстве — по ``index``).
        """
        ordered = sorted(items, key=lambda it: (-it.score.value, it.index))
        if top_n is None:
            return tuple(ordered)
        return tuple(ordered[: top_n.value])
