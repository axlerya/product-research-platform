"""Доменный сервис composer — составление текста документа.

Из товара берётся только контент-группа ``{name, brand, category,
description}``; коммерческие поля в текст не входят — поэтому смена
цены/остатка не меняет эмбеддинг (§5.1).
"""

from indexing_service.domain.value_objects.search_text import SearchText


def compose(
    *, name: str, brand: str, category: str, description: str
) -> SearchText:
    """Собирает поле-размеченный текст документа.

    Args:
        name: Название товара.
        brand: Бренд.
        category: Категория.
        description: Описание.

    Returns:
        Составной ``SearchText`` для dense и sparse эмбеддинга.
    """
    text = (
        f"Товар: {name}\n"
        f"Бренд: {brand}\n"
        f"Категория: {category}\n"
        f"Описание: {description}"
    )
    return SearchText(text)
