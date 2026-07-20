"""Спецификация коллекции Qdrant (§4): named-векторы + payload-индексы.

Имена векторов ``dense``/``sparse`` — кросс-сервисный контракт с
search-service (передаются в ``using=`` при hybrid-поиске). Sparse — без
``modifier=IDF`` (веса BGE-M3 уже финальные, §4.2).
"""

from qdrant_client import models

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"

# Payload-индексы (§4.4): фасеты, диапазоны, водяной знак.
PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("sku", models.PayloadSchemaType.KEYWORD),
    ("category", models.PayloadSchemaType.KEYWORD),
    ("brand", models.PayloadSchemaType.KEYWORD),
    ("supplier", models.PayloadSchemaType.KEYWORD),
    ("model_version", models.PayloadSchemaType.KEYWORD),
    ("price", models.PayloadSchemaType.FLOAT),
    ("cost", models.PayloadSchemaType.FLOAT),
    ("rating", models.PayloadSchemaType.FLOAT),
    ("margin_percent", models.PayloadSchemaType.FLOAT),
    ("stock", models.PayloadSchemaType.INTEGER),
    ("sales_per_month", models.PayloadSchemaType.INTEGER),
    ("review_count", models.PayloadSchemaType.INTEGER),
    ("aggregate_version", models.PayloadSchemaType.INTEGER),
    # Async-путь (chunked): владелец точки + версия текста (§9.4).
    ("product_id", models.PayloadSchemaType.KEYWORD),
    ("content_version", models.PayloadSchemaType.INTEGER),
    ("chunk_ix", models.PayloadSchemaType.INTEGER),
    ("in_stock", models.PayloadSchemaType.BOOL),
    ("is_deleted", models.PayloadSchemaType.BOOL),
    ("indexed_at", models.PayloadSchemaType.DATETIME),
)


def vectors_config(dim: int) -> dict[str, models.VectorParams]:
    """Конфигурация dense-вектора (cosine; BGE-M3 нормирован)."""
    return {
        DENSE_VECTOR: models.VectorParams(
            size=dim, distance=models.Distance.COSINE
        )
    }


def sparse_vectors_config() -> dict[str, models.SparseVectorParams]:
    """Конфигурация sparse-вектора БЕЗ ``modifier=IDF`` (§4.2)."""
    return {SPARSE_VECTOR: models.SparseVectorParams()}
