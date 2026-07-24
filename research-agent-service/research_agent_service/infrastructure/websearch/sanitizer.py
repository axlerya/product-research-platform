"""HtmlContentSanitizer — обеззараживание недоверенного текста."""

import re
from html.parser import HTMLParser

_MAX_LENGTH = 2000
_DROP_TAGS = frozenset({"script", "style", "noscript", "template", "head"})
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Извлекает видимый текст, отбрасывая script/style и т.п."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in _DROP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def extracted_text(self) -> str:
        return "".join(self._chunks)


class HtmlContentSanitizer:
    """Убирает HTML/скрипты/скрытые символы, нормализует и обрезает.

    Возвращает безопасный для показа текст: теги вырезаны, содержимое
    script/style отброшено, управляющие символы удалены, пробелы
    схлопнуты, длина ограничена.
    """

    def __init__(self, *, max_length: int = _MAX_LENGTH) -> None:
        self._max_length = max_length

    def sanitize(self, raw: str) -> str:
        """Возвращает обеззараженный текст."""
        extractor = _TextExtractor()
        extractor.feed(raw)
        text = extractor.extracted_text()
        text = _CONTROL.sub("", text)
        text = _WHITESPACE.sub(" ", text).strip()
        return text[: self._max_length]
