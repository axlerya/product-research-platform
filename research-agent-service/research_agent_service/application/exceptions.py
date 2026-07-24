"""Прикладные исключения — сигналы деградации ведомых зависимостей."""


class ApplicationError(Exception):
    """Базовое прикладное исключение."""


class RerankerUnavailable(ApplicationError):
    """Reranker недоступен — retrieval деградирует до порядка RRF."""


class CatalogUnavailable(ApplicationError):
    """catalog-service недоступен — цены берём из read-model с пометкой."""
