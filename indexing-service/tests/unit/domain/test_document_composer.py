"""Тесты доменного сервиса ``compose`` — составление текста документа."""

from indexing_service.domain.services.document_composer import compose
from indexing_service.domain.value_objects.search_text import SearchText


def test_compose_includes_labeled_fields():
    text = compose(
        name="Наушники",
        brand="AudioMax",
        category="Электроника",
        description="Беспроводные",
    )
    assert isinstance(text, SearchText)
    assert "Товар: Наушники" in text.value
    assert "Бренд: AudioMax" in text.value
    assert "Категория: Электроника" in text.value
    assert "Описание: Беспроводные" in text.value


def test_compose_is_deterministic():
    left = compose(name="N", brand="B", category="C", description="D")
    right = compose(name="N", brand="B", category="C", description="D")
    assert left == right
