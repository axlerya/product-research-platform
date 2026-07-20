"""Конвертация lexical_weights BGE-M3 → доменный ``SparseVector``."""

from collections.abc import Mapping

from embedding_service.domain.value_objects.sparse_vector import SparseVector


def lexical_weights_to_sparse(weights: Mapping[str, float]) -> SparseVector:
    """Строит ``SparseVector`` из lexical_weights BGE-M3.

    BGE-M3 отдаёт словарь ``{token_id_str: weight}``. Токен-id приводится к
    ``int``; каноничная форма (сортировка, отброс нулей) гарантируется
    фабрикой ``from_mapping``.

    Args:
        weights: Отображение токен-id (строкой) в вес.

    Returns:
        Канонический разрежённый вектор.
    """
    return SparseVector.from_mapping(
        {int(token): float(weight) for token, weight in weights.items()}
    )
