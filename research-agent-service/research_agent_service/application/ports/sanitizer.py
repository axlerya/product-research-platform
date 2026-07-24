"""Порт ContentSanitizerPort — обеззараживание недоверенного контента."""

from typing import Protocol


class ContentSanitizerPort(Protocol):
    """Санитайзер недоверенного текста (HTML, скрипты, скрытый текст)."""

    def sanitize(self, raw: str) -> str:
        """Возвращает безопасную для показа версию текста."""
        ...
