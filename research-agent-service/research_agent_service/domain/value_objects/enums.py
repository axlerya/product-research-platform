"""Доменные enum-словари агента.

Замкнутые словари, разделяемые доменом, событиями и API. Все — StrEnum:
члены сериализуются как строки на границах без потери типа.
"""

from enum import StrEnum


class MessageRole(StrEnum):
    """Роль сообщения в диалоге."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class RunStatus(StrEnum):
    """Статус прогона агента над одним запросом."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


class ToolName(StrEnum):
    """Закрытый список инструментов агента (allowlist)."""

    PRODUCT_CATALOG_RAG = "product_catalog_rag"
    PRICE_ANALYSIS = "price_analysis"
    WEB_SEARCH = "web_search"


class ToolCallStatus(StrEnum):
    """Исход вызова инструмента."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    REJECTED = "rejected"


class CitationType(StrEnum):
    """Тип источника факта в ответе (инструмент, породивший факт)."""

    PRODUCT = "product"
    PRICE_ANALYSIS = "price_analysis"
    WEB = "web"


class Confidence(StrEnum):
    """Уверенность в ответе (считается детерминированно, не моделью)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FeedbackRating(StrEnum):
    """Оценка ответа пользователем."""

    UP = "up"
    DOWN = "down"


class ErrorCode(StrEnum):
    """Машиночитаемый код ошибки прогона."""

    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    VECTOR_SEARCH_FAILED = "vector_search_failed"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    LLM_UNAVAILABLE = "llm_unavailable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INVALID_QUERY = "invalid_query"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal"


class ErrorCategory(StrEnum):
    """Категория ошибки — для маршрутизации и метрик."""

    UPSTREAM = "upstream"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    BUDGET = "budget"
    INTERNAL = "internal"


class RunStage(StrEnum):
    """Стадия прогона, на которой произошло событие или ошибка."""

    GUARD = "guard"
    PLAN = "plan"
    RETRIEVAL = "retrieval"
    PRICE_ANALYSIS = "price_analysis"
    WEB_SEARCH = "web_search"
    FINALIZE = "finalize"
