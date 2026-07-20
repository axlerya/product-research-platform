"""Value object ``EmbeddingLimits`` — политика лимитов батча."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import InvalidLimitsError


@dataclass(frozen=True, slots=True)
class EmbeddingLimits:
    """Лимиты батча (свои экземпляры для DOCUMENT и QUERY).

    Все значения должны быть строго положительны.

    Attributes:
        max_texts: Максимум текстов в батче.
        max_text_chars: Максимум символов в одном тексте.
        max_tokens: Максимум токенов в одном тексте.
        max_total_bytes: Максимум суммарного размера запроса (UTF-8 байт).
    """

    max_texts: int
    max_text_chars: int
    max_tokens: int
    max_total_bytes: int

    def __post_init__(self) -> None:
        limits = {
            "max_texts": self.max_texts,
            "max_text_chars": self.max_text_chars,
            "max_tokens": self.max_tokens,
            "max_total_bytes": self.max_total_bytes,
        }
        for name, value in limits.items():
            if value <= 0:
                raise InvalidLimitsError(f"{name} должно быть > 0: {value}")
