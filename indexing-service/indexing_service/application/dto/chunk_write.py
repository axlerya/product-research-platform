"""DTO ``ChunkWrite`` — запрос на запись точки чанка в Qdrant (§9.4).

Application формирует его из успешного item результата; адаптер строит payload
с двумя водяными знаками (``aggregate_version`` + ``content_version``) и пишет
merge-семантикой, применяя guard по ``content_version``.
"""

from dataclasses import dataclass
from uuid import UUID

from indexing_service.application.dto.embedding_result import SparseData


@dataclass(frozen=True, slots=True)
class ChunkWrite:
    """Данные для записи одной точки чанка.

    Attributes:
        point_id: Идентификатор точки Qdrant (== ``text_id`` чанка).
        product_id: Товар-владелец (для фильтра/tombstone).
        sku: Артикул (в payload для отладки).
        chunk_ix: Порядковый индекс чанка внутри товара.
        content_version: Версия текста, на которой считались векторы (guard).
        aggregate_version: Версия агрегата товара.
        content_hash: Хэш реально проэмбеженного текста (водяной знак).
        model_version: Ключ модели embedding-service (водяной знак).
        dense: Плотный вектор или ``None``.
        sparse: Разреженный вектор или ``None``.
        token_count: Число токенов или ``None``.
        collection: Целевая коллекция (reindex) или ``None`` — писать в
            alias. Без неё результаты эпохи reindex ушли бы в живой индекс.
    """

    point_id: str
    product_id: UUID
    sku: str
    chunk_ix: int
    content_version: int
    aggregate_version: int
    content_hash: str
    model_version: str
    dense: tuple[float, ...] | None
    sparse: SparseData | None
    token_count: int | None
    collection: str | None = None
