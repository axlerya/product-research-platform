"""Value objects Query и QueryFilters — валидированный вход агента."""

from dataclasses import dataclass
from decimal import Decimal

from research_agent_service.domain.exceptions import (
    EmptyQuery,
    InvalidQuery,
    QueryTooLong,
)

# Верхний предел длины пользовательского запроса (символов).
MAX_QUERY_CHARS = 4000


@dataclass(frozen=True, slots=True)
class QueryFilters:
    """Безопасное подмножество фасетов — только индексированные поля.

    Всё опционально; заданные значения сужают поиск/анализ. Диапазонные
    пары проверяются на согласованность (min <= max).
    """

    category: str | None = None
    brand: str | None = None
    supplier: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock: bool | None = None
    min_rating: Decimal | None = None
    margin_min: Decimal | None = None
    margin_max: Decimal | None = None

    def __post_init__(self) -> None:
        self._ensure_range(self.price_min, self.price_max, "price")
        self._ensure_range(self.margin_min, self.margin_max, "margin")

    @staticmethod
    def _ensure_range(
        low: Decimal | None, high: Decimal | None, name: str
    ) -> None:
        if low is not None and high is not None and low > high:
            raise InvalidQuery(f"{name}_min не может быть больше {name}_max")


@dataclass(frozen=True, slots=True)
class Query:
    """Валидированный запрос пользователя.

    Attributes:
        text: Текст запроса (обрезается по краям, 1..MAX_QUERY_CHARS).
        locale: Локаль ответа.
        filters: Необязательные фасеты поиска.
        idempotency_key: Ключ идемпотентности от клиента.
    """

    text: str
    locale: str = "ru"
    filters: QueryFilters | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        stripped = self.text.strip()
        if not stripped:
            raise EmptyQuery("Запрос не может быть пустым")
        if len(stripped) > MAX_QUERY_CHARS:
            raise QueryTooLong(f"Запрос длиннее {MAX_QUERY_CHARS} символов")
        object.__setattr__(self, "text", stripped)
