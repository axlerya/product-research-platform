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
    """Итоги постановки эпохи переиндексации (§8, Q6).

    Reindex больше не индексирует сам: он заводит задания, а векторы считает
    embedding-service. Поэтому отчёт — о поставленном, а не о записанном.

    Attributes:
        queued: Заведено заданий на эмбеддинг.
        skipped: Задание уже было (повторный запуск эпохи).
        errors: Ошибки обработки.
    """

    queued: int = 0
    skipped: int = 0
    errors: int = 0


@dataclass(frozen=True, slots=True)
class SwapReport:
    """Итоги попытки переключить alias на новую коллекцию (Q6).

    Attributes:
        swapped: Переключён ли alias.
        total: Всего заданий в эпохе.
        done: Завершено успешно.
        failed: Завершено с отказом.
        pending: Ещё в работе.
    """

    swapped: bool = False
    total: int = 0
    done: int = 0
    failed: int = 0
    pending: int = 0
