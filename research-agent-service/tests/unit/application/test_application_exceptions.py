"""Тесты прикладных исключений деградации."""

from research_agent_service.application.exceptions import (
    ApplicationError,
    CatalogUnavailable,
    RerankerUnavailable,
)


def test_degradation_exceptions_are_application_errors() -> None:
    """Сигналы деградации наследуют базовое прикладное исключение."""
    assert issubclass(RerankerUnavailable, ApplicationError)
    assert issubclass(CatalogUnavailable, ApplicationError)
