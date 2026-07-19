"""Отчёты batch use cases (reindex/reconcile)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Итоги сверки каталога и Qdrant (§9).

    Attributes:
        matched: Совпало (актуально).
        indexed: Было в каталоге, не было в Qdrant → проиндексировано.
        repaired: Дрейф версии/метрик/контента → починено.
        tombstoned: Осиротевшие точки (нет в каталоге) → tombstone.
        errors: Ошибки обработки.
    """

    matched: int = 0
    indexed: int = 0
    repaired: int = 0
    tombstoned: int = 0
    errors: int = 0


@dataclass(frozen=True, slots=True)
class ReindexReport:
    """Итоги полной переиндексации (§8).

    Attributes:
        indexed: Проиндексировано товаров в новую коллекцию.
        errors: Ошибки обработки.
    """

    indexed: int = 0
    errors: int = 0
