"""Детерминированные идентификаторы точек чанков (§9.1).

Идентичность чанка обязана быть воспроизводимой: повторная обработка того же
события каталога или тот же rechunk должны давать те же ``point_id``, иначе
в Qdrant копятся дубликаты-сироты.

Нулевой под-чанк намеренно переиспользует точку родителя: иначе после
дробления исходная точка товара осталась бы с устаревшими векторами, а
удалить её нельзя — на ней лежит коммерческий payload (§9.4).
"""

from uuid import UUID, uuid5

# Стабильное пространство имён (не менять — иначе поедут все point_id).
_NAMESPACE = UUID("2f9a6c53-7b18-4d0a-9c64-1e5f8a3b7d20")


def chunk_point_id(product_id: UUID, chunk_ix: int) -> str:
    """Возвращает ``point_id`` чанка товара.

    Нулевой чанк — это сама точка товара: на ней лежит коммерческий payload,
    который пишет горячий путь, и туда же async-результат домержит векторы.

    Args:
        product_id: Идентификатор товара.
        chunk_ix: Порядковый индекс чанка, начиная с нуля.

    Returns:
        Для ``chunk_ix == 0`` — UUID товара строкой, иначе производный UUID.
    """
    if chunk_ix < 0:
        raise ValueError(f"chunk_ix < 0: {chunk_ix}")
    if chunk_ix == 0:
        return str(product_id)
    return str(uuid5(_NAMESPACE, f"{product_id}|{chunk_ix}"))


def subchunk_point_id(parent_point_id: str, index: int) -> str:
    """Возвращает ``point_id`` под-чанка при rechunk.

    Args:
        parent_point_id: Точка исходного (слишком длинного) чанка.
        index: Порядковый номер под-чанка, начиная с нуля.

    Returns:
        Для ``index == 0`` — точка родителя, иначе производный UUID строкой.
    """
    if index < 0:
        raise ValueError(f"index < 0: {index}")
    if index == 0:
        return parent_point_id
    return str(uuid5(_NAMESPACE, f"{parent_point_id}|{index}"))
