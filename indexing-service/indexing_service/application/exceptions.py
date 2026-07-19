"""Прикладные исключения индексатора.

Делятся на постоянные (poison → DLQ) и временные (retry). Разделение
управляет ack-политикой консюмера (§7.1): постоянные не ретраятся.
"""


class IndexingError(Exception):
    """Корень прикладных ошибок индексатора."""


class PermanentError(IndexingError):
    """Неустранимая ошибка — сообщение уходит в DLQ, не ретраится."""


class TransientError(IndexingError):
    """Временная ошибка — сообщение ретраится с backoff (§7)."""


class EventValidationError(PermanentError):
    """Событие не прошло разбор/доменную валидацию (poison)."""


class ProductNotInCatalog(PermanentError):
    """Repair не нашёл товар в catalog — индексировать нечего."""


class EmbeddingError(TransientError):
    """Сбой построения эмбеддингов."""


class VectorIndexError(TransientError):
    """Сбой обращения к Qdrant."""


class CatalogUnavailableError(TransientError):
    """catalog-service недоступен (repair/reindex/reconcile)."""
