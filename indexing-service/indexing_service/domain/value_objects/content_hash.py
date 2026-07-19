"""Value object ``ContentHash`` — sha256 составного текста документа."""

import hashlib
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class ContentHash:
    """Хэш текста для дешёвого детекта изменения контента.

    Позволяет пропустить ре-эмбеддинг, если текст не изменился (§6.3).

    Attributes:
        value: Шестнадцатеричный sha256 (64 символа).
    """

    value: str

    @classmethod
    def of(cls, text: str) -> Self:
        """Считает ``ContentHash`` от текста (UTF-8, sha256)."""
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return cls(digest)
