"""Read-side DTO (проекции для чтения, CQRS-lite)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MoneyView:
    """Деньги в проекции чтения."""

    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class MarginView:
    """Маржа в проекции чтения (percent = None при нулевой цене)."""

    profit: MoneyView
    percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProductView:
    """Денормализованное представление товара для чтения."""

    id: UUID
    sku: str
    name: str
    description: str
    category: str
    brand: str
    supplier: str
    price: MoneyView
    cost: MoneyView
    stock: int
    is_in_stock: bool
    sales_per_month: int
    avg_rating: Decimal
    review_count: int
    margin: MarginView
    source_updated_at: date | None
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Page[T]:
    """Страница результатов (offset-пагинация)."""

    items: tuple[T, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class ProductBatchView:
    """Результат batch-чтения по списку артикулов.

    Attributes:
        products: Найденные товары в порядке запрошенных артикулов.
        missing_skus: Нормализованные артикулы, которых нет в каталоге.
    """

    products: tuple[ProductView, ...]
    missing_skus: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriceStatsView:
    """Статистика цен среза (в единой валюте среза)."""

    min: Decimal
    max: Decimal
    avg: Decimal
    median: Decimal
    stddev: Decimal


@dataclass(frozen=True, slots=True)
class MarginStatsView:
    """Статистика маржи среза в процентах плюс счётчики особых случаев."""

    min_percent: Decimal
    max_percent: Decimal
    avg_percent: Decimal
    median_percent: Decimal
    undefined_count: int
    negative_count: int


@dataclass(frozen=True, slots=True)
class MarginBandView:
    """Бэнд маржи с числом попавших в него товаров."""

    label: str
    count: int
    lower_percent: Decimal | None = None
    upper_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PriceOutlierView:
    """Ценовой выброс: товар, цена, направление и скор отклонения."""

    sku: str
    price: MoneyView
    reason: str
    score: Decimal


@dataclass(frozen=True, slots=True)
class PriceAnalysisView:
    """Готовый детерминированный ценовой анализ среза.

    Attributes:
        count: Число товаров в срезе.
        currency: Валюта среза.
        price: Статистика цен.
        margin: Статистика маржи.
        analysis_ref: Детерминированный идентификатор среза (provenance).
        bands: Распределение по бэндам маржи.
        outliers: Ценовые выбросы.
    """

    count: int
    currency: str
    price: PriceStatsView
    margin: MarginStatsView
    analysis_ref: str
    bands: tuple[MarginBandView, ...] = ()
    outliers: tuple[PriceOutlierView, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceView:
    """Элемент справочника с числом товаров."""

    id: UUID
    name: str
    product_count: int


@dataclass(frozen=True, slots=True)
class CategoryMarginRow:
    """Агрегат маржинальности по категории."""

    category: str
    product_count: int
    avg_margin_percent: Decimal | None
    min_margin_percent: Decimal | None
    max_margin_percent: Decimal | None
