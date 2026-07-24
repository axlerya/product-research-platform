"""Доменные исключения агента."""


class DomainError(Exception):
    """Базовое доменное исключение."""


class InvalidCitation(DomainError):
    """Некорректный источник факта (citation)."""
