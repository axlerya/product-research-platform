"""Перевод доменных исключений в прикладные (мост domain → application).

Домен не знает про ``CatalogError``, поэтому мост живёт в application и
вызывается внутри use cases вокруг доменных операций.
"""

from catalog_service.application.exceptions import (
    BusinessRuleViolation,
    CatalogError,
    ValidationError,
)
from catalog_service.domain.exceptions import (
    CurrencyMismatchError,
    DomainError,
    InvalidCurrencyError,
    InvalidRatingError,
    InvalidSku,
    NegativeCostError,
    NegativeMetricError,
    NegativePriceError,
    NegativeStockError,
)

_VALUE_ERRORS = (
    InvalidSku,
    InvalidCurrencyError,
    NegativePriceError,
    NegativeCostError,
    NegativeStockError,
    InvalidRatingError,
    NegativeMetricError,
    CurrencyMismatchError,
)


def to_catalog_error(exc: DomainError) -> CatalogError:
    """Переводит доменную ошибку в прикладную.

    Args:
        exc: Доменное исключение.

    Returns:
        ``ValidationError`` для ошибок значения VO, иначе
        ``BusinessRuleViolation``.
    """
    meta = {"domain_error": type(exc).__name__}
    if isinstance(exc, _VALUE_ERRORS):
        return ValidationError(str(exc), meta=meta)
    return BusinessRuleViolation(str(exc), meta=meta)
