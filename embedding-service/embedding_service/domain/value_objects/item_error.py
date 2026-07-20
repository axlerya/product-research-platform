"""Value objects ``EmbeddingErrorCode`` / ``ItemError`` — отказ по элементу."""

from dataclasses import dataclass
from enum import Enum


class EmbeddingErrorCode(Enum):
    """Код доменного отказа по элементу батча (едет в событие-результат)."""

    EMPTY_TEXT = "EMPTY_TEXT"
    TEXT_TOO_LONG = "TEXT_TOO_LONG"
    TOKENS_EXCEEDED = "TOKENS_EXCEEDED"
    INFERENCE_FAILED = "INFERENCE_FAILED"


@dataclass(frozen=True, slots=True)
class ItemError:
    """Описание отказа по одному элементу батча.

    Attributes:
        code: Код отказа.
        message: Человекочитаемое пояснение.
    """

    code: EmbeddingErrorCode
    message: str
