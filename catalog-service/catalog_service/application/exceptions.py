"""Прикладные исключения — единственная иерархия, транслируемая в HTTP.

Домен бросает ``DomainError``; прикладной слой переводит их в
``CatalogError`` (см. ``_translate``); presentation — в RFC 9457.
"""

from typing import Any


class CatalogError(Exception):
    """Корень прикладных ошибок.

    Attributes:
        code: Машинный код ошибки (стабильный контракт для клиента).
        message: Человекочитаемое сообщение.
        meta: Дополнительные детали (sku, версии и т.п.).
    """

    code: str = "catalog_error"

    def __init__(
        self, message: str, *, meta: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.meta = meta or {}


class NotFoundError(CatalogError):
    """Ресурс не найден (HTTP 404)."""

    code = "not_found"


class ProductNotFound(NotFoundError):
    """Товар не найден."""

    code = "product_not_found"


class CategoryNotFound(NotFoundError):
    """Категория не найдена."""

    code = "category_not_found"


class BrandNotFound(NotFoundError):
    """Бренд не найден."""

    code = "brand_not_found"


class SupplierNotFound(NotFoundError):
    """Поставщик не найден."""

    code = "supplier_not_found"


class ConflictError(CatalogError):
    """Конфликт состояния (HTTP 409)."""

    code = "conflict"


class ConcurrencyConflict(ConflictError):
    """Оптимистичная блокировка сорвалась (версия не совпала)."""

    code = "concurrency_conflict"


class DuplicateSku(ConflictError):
    """Товар с таким артикулом уже существует."""

    code = "duplicate_sku"


class ValidationError(CatalogError):
    """Значение не прошло доменную валидацию (HTTP 422)."""

    code = "validation_error"


class BusinessRuleViolation(CatalogError):
    """Нарушено бизнес-правило перехода состояния (HTTP 400)."""

    code = "business_rule_violation"


# Дословный алиас к канону: StaleVersionError == ConcurrencyConflict.
StaleVersionError = ConcurrencyConflict
