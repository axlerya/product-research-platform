"""Доменные исключения reranking.

Специфичные для reranker инварианты, которых нет в embedding-домене.
Наследуются от общего корня ``DomainError`` — application/presentation ловят
его единообразно. Общие для домена ошибки (пустой текст, лимиты, размер
батча) переиспользуются из ``domain.exceptions`` без дублирования.
"""

from embedding_service.domain.exceptions import DomainError


class InvalidScoreError(DomainError):
    """Скор релевантности не является конечным числом."""


class InvalidTopNError(DomainError):
    """``top_n`` не является положительным числом."""


class InvalidRankedItemError(DomainError):
    """Нарушен инвариант ранжированного элемента (например, индекс < 0)."""
