"""Value object ``EmbeddingText`` — нормализованный непустой текст."""

from dataclasses import dataclass

from embedding_service.domain.exceptions import EmptyTextError


@dataclass(frozen=True, slots=True)
class EmbeddingText:
    """Текст элемента батча.

    На входе ``strip``; пустая строка или строка из одних пробелов
    отвергается. Абсолютные лимиты длины — политика ``EmbeddingLimits``.

    Attributes:
        value: Очищенный текст.
    """

    value: str

    def __post_init__(self) -> None:
        stripped = self.value.strip()
        if not stripped:
            raise EmptyTextError("Текст не может быть пустым")
        object.__setattr__(self, "value", stripped)

    @property
    def char_length(self) -> int:
        """Длина текста в символах (после нормализации)."""
        return len(self.value)
