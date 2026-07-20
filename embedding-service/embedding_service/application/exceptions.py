"""Прикладные исключения embedding-service и мосты из домена.

Иерархия ``ApplicationError`` → ``PermanentError`` | ``TransientError``. Две
базы задают единственную ось «park vs retry»: RabbitMQ-диспетчер ловит их
базами, gRPC-интерсептор отображает конкретные типы в разные status codes.
"""

from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    DomainError,
    EmptyBatchError,
    EmptyTextError,
    RequestTooLargeError,
    TextTooLongError,
    TokensExceededError,
)
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
    ItemError,
)


class ApplicationError(Exception):
    """Корень прикладных ошибок."""


class PermanentError(ApplicationError):
    """Не ретраим (poison): валидация, битая схема, провал probe."""


class TransientError(ApplicationError):
    """Ретраим: инференс/OOM/таймаут/перегрузка/модель не готова."""


class ValidationError(PermanentError):
    """Мост доменных валидаций входа (fail-fast)."""

    def __init__(self, message: str, *, domain_type: str | None = None) -> None:
        super().__init__(message)
        self.domain_type = domain_type


class ProbeFailed(PermanentError):
    """Провал probe/устройства при старте (dim/sparse/CUDA недоступна)."""


class InferenceError(TransientError):
    """Непредвиденный сбой инференса (encode/CUDA после split-retry)."""


class InferenceTimeoutError(TransientError):
    """Превышен пер-батч таймаут инференса."""


class InferenceOverloadedError(TransientError):
    """Переполнена очередь ожидания (backpressure)."""

    def __init__(self, *, queue_depth: int | None = None) -> None:
        super().__init__(
            f"очередь инференса переполнена (глубина {queue_depth})"
        )
        self.queue_depth = queue_depth


class ModelNotReadyError(TransientError):
    """Модель ещё грузится или деградирует."""


_VALIDATION_ERRORS: tuple[type[DomainError], ...] = (
    EmptyTextError,
    TextTooLongError,
    TokensExceededError,
    EmptyBatchError,
    BatchTooLargeError,
    RequestTooLargeError,
)

_ITEM_CODE: dict[type[DomainError], EmbeddingErrorCode] = {
    EmptyTextError: EmbeddingErrorCode.EMPTY_TEXT,
    TextTooLongError: EmbeddingErrorCode.TEXT_TOO_LONG,
    TokensExceededError: EmbeddingErrorCode.TOKENS_EXCEEDED,
}


def to_application_error(exc: DomainError) -> ApplicationError:
    """Домен → application.

    Валидация входа → ``ValidationError`` (fail-fast транспорта); дефект
    формы/конфига (``InvalidVectorError``/``InvalidModelIdError``/…) →
    ``InferenceError`` (транзиент — это дефект инференса, не пользователя).
    """
    if isinstance(exc, _VALIDATION_ERRORS):
        return ValidationError(str(exc), domain_type=type(exc).__name__)
    return InferenceError(str(exc))


def to_item_error(exc: DomainError) -> ItemError:
    """Пер-элементный отказ документа → ``ItemError`` (партиал)."""
    code = _ITEM_CODE.get(type(exc), EmbeddingErrorCode.INFERENCE_FAILED)
    return ItemError(code=code, message=str(exc))
