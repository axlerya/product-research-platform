"""Доменные исключения — нарушения инвариантов агрегата и VO.

Чистый stdlib, без HTTP и кодов транспорта. Прикладной слой ловит эти
исключения и переводит в свои (``CatalogError``); presentation — в HTTP.
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


class ProductAlreadyDeleted(DomainError):
    """Защитный guard: недопустимый переход для удалённого товара.

    Метод ``Product.delete`` его НЕ бросает: удаление идемпотентно —
    повтор на уже удалённом товаре это no-op.
    """
