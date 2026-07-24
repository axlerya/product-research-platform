"""DTO ценового анализа (вход-селектор и готовый результат из catalog).

Все числа приходят из catalog уже посчитанными: медиана, стандартное
отклонение, бэнды маржи и выбросы. Агент их не вычисляет (INV-1) — только
переносит на границе адаптера (строки → Decimal).
"""

from dataclasses import dataclass
from decimal import Decimal

from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.money import Money


@dataclass(frozen=True, slots=True)
class ProductSelector:
    """Отбор товаров для анализа: явный список sku ИЛИ фасеты."""

    skus: tuple[str, ...] = ()
    category: str | None = None
    brand: str | None = None
    supplier: str | None = None
    text: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock: bool | None = None
    min_rating: Decimal | None = None
    margin_min: Decimal | None = None
    margin_max: Decimal | None = None
    include_deleted: bool = False


@dataclass(frozen=True, slots=True)
class MarginBandSpec:
    """Границы одного бэнда маржи (проценты)."""

    label: str
    lower_percent: Decimal | None = None
    upper_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PriceStats:
    """Статистика цен в валюте результата."""

    min: Decimal
    max: Decimal
    avg: Decimal
    median: Decimal
    stddev: Decimal


@dataclass(frozen=True, slots=True)
class MarginStats:
    """Статистика маржи (проценты) плюс счётчики особых случаев."""

    min_percent: Decimal
    max_percent: Decimal
    avg_percent: Decimal
    median_percent: Decimal
    undefined_count: int
    negative_count: int


@dataclass(frozen=True, slots=True)
class MarginBand:
    """Бэнд маржи с числом попавших товаров."""

    label: str
    count: int
    lower_percent: Decimal | None = None
    upper_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Outlier:
    """Ценовой выброс: товар, цена, причина и скор."""

    sku: str
    price: Money
    reason: str
    score: Decimal


@dataclass(frozen=True, slots=True)
class PriceAnalysisResult:
    """Готовый детерминированный результат анализа цен из catalog.

    Attributes:
        count: Число товаров в срезе.
        currency: Валюта статистики (единая для среза).
        price: Статистика цен.
        margin: Статистика маржи.
        analysis_ref: Детерминированный id среза (provenance цитаты, INV-2).
        bands: Бэнды маржи.
        outliers: Ценовые выбросы.
    """

    count: int
    currency: Currency
    price: PriceStats
    margin: MarginStats
    analysis_ref: str
    bands: tuple[MarginBand, ...] = ()
    outliers: tuple[Outlier, ...] = ()
