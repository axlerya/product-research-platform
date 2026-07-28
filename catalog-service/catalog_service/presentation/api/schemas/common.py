"""Общие типы и схемы: деньги/рейтинг строкой, результат команды, ошибка."""

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer

# Деньги и рейтинг сериализуются в JSON строкой (без потери точности).
Amount = Annotated[
    Decimal,
    Field(max_digits=12, decimal_places=2, ge=0),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]
RatingValue = Annotated[
    Decimal,
    Field(max_digits=3, decimal_places=2, ge=0, le=5),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]

PercentOpt = Annotated[
    Decimal | None,
    Field(max_digits=5, decimal_places=2),
    PlainSerializer(
        lambda v: None if v is None else f"{v:.2f}",
        return_type=str | None,
        when_used="json",
    ),
]

# Проценты в ответах аналитики. Точность на входе не ограничиваем: значение
# либо посчитано нами (уже округлено), либо возвращается эхом из запроса —
# ограничение колонки products.margin_percent тут не при чём.
StatPercent = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]
StatPercentOpt = Annotated[
    Decimal | None,
    PlainSerializer(
        lambda v: None if v is None else f"{v:.2f}",
        return_type=str | None,
        when_used="json",
    ),
]

SKU_PATTERN = r"^[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]$"
SkuField = Annotated[
    str, Field(pattern=SKU_PATTERN, min_length=3, max_length=64)
]


class WriteResult(BaseModel):
    """Тонкий ответ команды: идентификатор, артикул, актуальная версия."""

    id: UUID
    sku: str
    version: int


class FieldError(BaseModel):
    """Ошибка валидации отдельного поля."""

    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """Тело ошибки по RFC 9457 (``application/problem+json``)."""

    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = None
    meta: dict[str, Any] | None = None
