"""Доменные исключения embedding-service.

Все наследуются от корня ``DomainError``. Чистый stdlib, без транспортной
семантики: маппинг в gRPC status / RabbitMQ ack-retry-park делают application
и presentation, домен про них не знает.
"""


class DomainError(Exception):
    """Корень доменных ошибок."""


class EmptyTextError(DomainError):
    """Пустой или состоящий из одних пробелов текст/идентификатор."""


class InvalidVectorError(DomainError):
    """Нарушен инвариант формы вектора/результата."""


class InvalidModelIdError(DomainError):
    """Некорректные поля идентификатора модели."""


class EmptyBatchError(DomainError):
    """Батч без элементов."""


class BatchTooLargeError(DomainError):
    """Число текстов превышает лимит."""


class TextTooLongError(DomainError):
    """Длина текста превышает лимит символов."""


class RequestTooLargeError(DomainError):
    """Суммарный размер запроса превышает лимит байт."""


class TokensExceededError(DomainError):
    """Число токенов превышает лимит."""


class InvalidLimitsError(DomainError):
    """Некорректная политика лимитов (значение <= 0)."""
