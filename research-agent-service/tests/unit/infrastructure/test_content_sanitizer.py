"""Тесты HtmlContentSanitizer."""

from research_agent_service.infrastructure.websearch.sanitizer import (
    HtmlContentSanitizer,
)


def test_strips_html_tags() -> None:
    """HTML-теги вырезаются, остаётся текст."""
    assert HtmlContentSanitizer().sanitize("<b>Наушники</b>") == "Наушники"


def test_drops_script_content() -> None:
    """Содержимое script отбрасывается целиком."""
    raw = "цена<script>alert('x')</script> низкая"

    assert HtmlContentSanitizer().sanitize(raw) == "цена низкая"


def test_collapses_whitespace() -> None:
    """Переводы строк и пробелы схлопываются в один пробел."""
    assert HtmlContentSanitizer().sanitize("a\n\n   b\tc") == "a b c"


def test_removes_control_characters() -> None:
    """Управляющие символы удаляются."""
    assert HtmlContentSanitizer().sanitize("текст\x00\x07конец") == (
        "текстконец"
    )


def test_decodes_entities() -> None:
    """HTML-сущности декодируются."""
    assert HtmlContentSanitizer().sanitize("Tom &amp; Jerry") == "Tom & Jerry"


def test_truncates_to_max_length() -> None:
    """Длинный текст обрезается до лимита."""
    sanitizer = HtmlContentSanitizer(max_length=5)

    assert sanitizer.sanitize("абвгдежз") == "абвгд"
