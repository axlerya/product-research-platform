"""Доменные исключения — нарушения инвариантов VO и сущностей проекции.

Чистый stdlib, без транспортных кодов. Прикладной слой ловит их и
переводит в свои исключения; presentation — в HTTP/ack-политику консюмера.
"""


class DomainError(Exception):
    """Корень иерархии доменных ошибок."""


class InvalidSku(DomainError):
    """Некорректный артикул (SKU): не проходит нормализацию/regex."""


class InvalidCurrencyError(DomainError):
    """Код валюты не соответствует ISO-4217 alpha-3 (``^[A-Z]{3}$``)."""


class NegativePriceError(DomainError):
    """Цена меньше нуля."""


class NegativeCostError(DomainError):
    """Себестоимость меньше нуля."""


class NegativeStockError(DomainError):
    """Остаток на складе меньше нуля."""


class InvalidRatingError(DomainError):
    """Рейтинг вне диапазона [0..5]."""


class NegativeMetricError(DomainError):
    """Товарная метрика (продажи/отзывы) меньше нуля."""


class CurrencyMismatchError(DomainError):
    """Операция над деньгами в разных валютах."""


class InvalidDocumentError(DomainError):
    """Пустой или некорректный текст поискового документа."""


class InvalidVectorError(DomainError):
    """Некорректный dense/sparse вектор (форма/значения/размерность)."""


class InvalidModelIdError(DomainError):
    """Некорректный идентификатор модели эмбеддингов."""


class InvalidWatermarkError(DomainError):
    """Некорректный водяной знак индексации (версия < 1)."""


class InvalidJobError(DomainError):
    """Некорректное состояние indexing job."""


class InvalidRequestError(DomainError):
    """Некорректная команда на эмбеддинг."""
