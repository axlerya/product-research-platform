"""Тесты перевода доменных исключений в прикладные."""

from catalog_service.application._translate import to_catalog_error
from catalog_service.application.exceptions import (
    BusinessRuleViolation,
    ValidationError,
)
from catalog_service.domain.exceptions import (
    NegativePriceError,
    ProductAlreadyDeleted,
)


def test_value_error_becomes_validation_error():
    result = to_catalog_error(NegativePriceError("цена < 0"))
    assert isinstance(result, ValidationError)
    assert result.meta["domain_error"] == "NegativePriceError"


def test_other_domain_error_becomes_business_rule_violation():
    result = to_catalog_error(ProductAlreadyDeleted("уже удалён"))
    assert isinstance(result, BusinessRuleViolation)
    assert result.meta["domain_error"] == "ProductAlreadyDeleted"
