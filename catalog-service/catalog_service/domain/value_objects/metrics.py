"""Value object ``ProductMetrics`` — товарные метрики."""

from dataclasses import dataclass

from catalog_service.domain.exceptions import NegativeMetricError
from catalog_service.domain.value_objects.rating import Rating


@dataclass(frozen=True, slots=True)
class ProductMetrics:
    """Метрики товара: продажи в месяц, рейтинг, число отзывов.

    Attributes:
        sales_per_month: Продажи за месяц (>= 0).
        avg_rating: Средний рейтинг.
        review_count: Количество отзывов (>= 0).
    """

    sales_per_month: int
    avg_rating: Rating
    review_count: int

    def __post_init__(self) -> None:
        if self.sales_per_month < 0:
            raise NegativeMetricError(
                f"Продажи в месяц не могут быть < 0: {self.sales_per_month}"
            )
        if self.review_count < 0:
            raise NegativeMetricError(
                f"Число отзывов не может быть < 0: {self.review_count}"
            )
