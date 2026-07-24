"""Контракт коллекции Qdrant между indexing-service и research-agent-service.

Имена named-векторов, размерность и метрика — кросс-сервисная договорённость:
indexing пишет, агент читает через ``using=dense``/``using=sparse``. Любое
расхождение делает гибридный поиск пустым, не выдавая ошибки.
"""

import pytest

from tests.support.stand import Qdrant

pytestmark = pytest.mark.contract

_EXPECTED_DIM = 1024
_REQUIRED_PAYLOAD_INDEXES = {
    "sku",
    "category",
    "brand",
    "supplier",
    "price",
    "margin_percent",
    "stock",
    "in_stock",
    "is_deleted",
    "product_id",
    "model_version",
}


def test_dense_vector_named_and_sized(qdrant: Qdrant) -> None:
    """Плотный вектор называется dense, размерность 1024, метрика косинус."""
    params = qdrant.collection_info()["config"]["params"]

    assert set(params["vectors"]) == {"dense"}
    assert params["vectors"]["dense"]["size"] == _EXPECTED_DIM
    assert params["vectors"]["dense"]["distance"] == "Cosine"


def test_sparse_vector_named_and_without_idf(qdrant: Qdrant) -> None:
    """Разреженный вектор называется sparse и без модификатора IDF.

    Веса BGE-M3 уже финальные: включённый IDF пересчитал бы их и сломал
    сопоставимость скоров запроса и документа.
    """
    params = qdrant.collection_info()["config"]["params"]
    sparse = params.get("sparse_vectors") or {}

    assert set(sparse) == {"sparse"}
    assert (sparse["sparse"].get("modifier") or "none") == "none"


def test_payload_indexes_cover_agent_facets(qdrant: Qdrant) -> None:
    """Фасеты и фильтры агента опираются на проиндексированные поля."""
    schema = qdrant.collection_info().get("payload_schema") or {}

    assert _REQUIRED_PAYLOAD_INDEXES <= set(schema)
