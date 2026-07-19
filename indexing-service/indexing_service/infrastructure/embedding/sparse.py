"""Конвертация BGE-M3 lexical_weights → доменный ``SparseVector``."""

from collections.abc import Mapping

from indexing_service.domain.value_objects.sparse_vector import SparseVector


def lexical_weights_to_sparse(
    weights: Mapping[str, float],
) -> SparseVector:
    """Строит ``SparseVector`` из lexical_weights BGE-M3.

    BGE-M3 отдаёт словарь ``{token_id_str: weight}`` (спец-токены и нули
    уже отброшены моделью). Здесь токен-id приводится к ``int``; каноничная
    форма (сортировка, отброс нулей) гарантируется ``from_mapping``.

    Args:
        weights: Отображение токен-id (строкой) в вес.

    Returns:
        Разрежённый вектор.
    """
    return SparseVector.from_mapping(
        {int(token): float(weight) for token, weight in weights.items()}
    )
