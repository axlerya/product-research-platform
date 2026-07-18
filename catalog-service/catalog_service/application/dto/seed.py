"""DTO идемпотентного seed из CSV."""

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class RawProductRow:
    """Сырая строка CSV: все поля — строки или ``None``, плюс номер строки.

    Приведение типов и валидация выполняются в прикладном слое (граница
    «грязь -> чистый домен»), поэтому здесь только строки.
    """

    line_no: int
    sku: str | None
    name: str | None
    description: str | None
    category_name: str | None
    brand_name: str | None
    price: str | None
    cost: str | None
    stock: str | None
    sales_per_month: str | None
    avg_rating: str | None
    review_count: str | None
    supplier_name: str | None
    source_updated_at: str | None


class RowOutcome(StrEnum):
    """Исход обработки одной строки seed."""

    CREATED = "created"
    CONTENT_CHANGED = "content_changed"
    COMMERCIAL_CHANGED = "commercial_changed"
    BOTH = "both"
    METRICS_ONLY = "metrics_only"
    UNCHANGED = "unchanged"
    SKIPPED_STALE = "skipped_stale"


@dataclass(frozen=True, slots=True)
class RowError:
    """Ошибка обработки строки (в отчёт, не роняет прогон).

    Attributes:
        line_no: Номер строки в файле.
        sku: Артикул (если удалось прочитать).
        kind: ``parse`` | ``domain`` | ``duplicate_in_file``.
        message: Человекочитаемое описание.
    """

    line_no: int
    sku: str | None
    kind: str
    message: str


@dataclass(slots=True)
class SeedReport:
    """Агрегированный отчёт прогона seed."""

    total: int = 0
    created: int = 0
    content_changed: int = 0
    commercial_changed: int = 0
    both: int = 0
    metrics_only: int = 0
    unchanged: int = 0
    skipped_stale: int = 0
    events_emitted: int = 0
    errors: list[RowError] = field(default_factory=list)

    def record(self, outcome: RowOutcome) -> None:
        """Увеличивает счётчик соответствующего исхода на единицу."""
        setattr(self, outcome.value, getattr(self, outcome.value) + 1)
