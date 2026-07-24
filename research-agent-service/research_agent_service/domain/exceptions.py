"""Доменные исключения агента."""


class DomainError(Exception):
    """Базовое доменное исключение."""


class InvalidCitation(DomainError):
    """Некорректный источник факта (citation)."""


class InvalidQuery(DomainError):
    """Некорректный запрос пользователя или его фильтры."""


class EmptyQuery(InvalidQuery):
    """Пустой запрос."""


class QueryTooLong(InvalidQuery):
    """Запрос превышает лимит длины."""
