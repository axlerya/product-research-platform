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
    # Эпоха reindex: по ней гейт свапа считает готовые точки эпохи (§8, Q6).
    ("reindex_epoch", models.PayloadSchemaType.KEYWORD),
    ("in_stock", models.PayloadSchemaType.BOOL),
    ("is_deleted", models.PayloadSchemaType.BOOL),
    ("indexed_at", models.PayloadSchemaType.DATETIME),
)

PRODUCT_ID = "product_id"
CHUNK_IX = "chunk_ix"
CONTENT_VERSION = "content_version"
MODEL_VERSION = "model_version"
REINDEX_EPOCH = "reindex_epoch"
IS_DELETED = "is_deleted"


def _not_a_chunk() -> models.FieldCondition:
    """Условие «точка не является чанком» (``chunk_ix`` отсутствует или 0).

    Строгое ``chunk_ix == 0`` не годится: синхронный путь ``chunk_ix`` не
    пишет вовсе, и такое условие спрятало бы товары, которым ещё не
    посчитали векторы, — а это ровно те, кого сверка обязана найти.
    """
    return models.FieldCondition(key=CHUNK_IX, range=models.Range(gt=0))


def root_points_filter() -> models.Filter:
    """Только корневые точки товаров (для reconcile-скана, §9)."""
    return models.Filter(must_not=[_not_a_chunk()])


def product_points_filter(product_id: str) -> models.Filter:
    """Все точки одного товара: корневая и чанки (§9.4).

    Корневая точка берётся по id, а не только по полю ``product_id``:
    частичные payload'ы (tombstone, коммерческие поля) его не содержат, и
    фильтр «только по полю» молча не нашёл бы точку, созданную такими
    записями, — удаление товара стало бы no-op.
    """
    return models.Filter(
        should=[
            models.HasIdCondition(has_id=[product_id]),
            models.FieldCondition(
                key=PRODUCT_ID, match=models.MatchValue(value=product_id)
            ),
        ]
    )


def epoch_ready_filter(
    *, epoch: str, expected_model: str | None
) -> models.Filter:
    """Готовые корневые точки эпохи reindex (гейт свапа alias, Q6).

    Считаем только то, у чего векторы реально записаны: ``model_version`` и
    ``reindex_epoch`` ставит лишь тот путь, который применил результат
    эмбеддинга. Чанки исключаем — иначе один многочанковый товар прошёл бы
    гейт за нескольких.
    """
    must: list[models.Condition] = [
        models.FieldCondition(
            key=REINDEX_EPOCH, match=models.MatchValue(value=epoch)
        )
    ]
    must_not: list[models.Condition] = [
        _not_a_chunk(),
        models.IsEmptyCondition(
            is_empty=models.PayloadField(key=CONTENT_VERSION)
        ),
        models.FieldCondition(
            key=IS_DELETED, match=models.MatchValue(value=True)
        ),
    ]
    if expected_model is not None:
        must.append(
            models.FieldCondition(
                key=MODEL_VERSION,
                match=models.MatchValue(value=expected_model),
            )
        )
    else:
        must_not.append(
            models.IsEmptyCondition(
                is_empty=models.PayloadField(key=MODEL_VERSION)
            )
        )
    return models.Filter(must=must, must_not=must_not)


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
