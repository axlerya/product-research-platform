"""DTO ``EmbeddingJobRequest`` — вход фазы A (постановка job, §6).

Собирается горячим путём из события каталога или из снимка товара и несёт
ровно то, что нужно для задания на эмбеддинг: кого индексируем, на какой
версии текста и какой текст эмбеддить. Коммерческие поля сюда не входят —
они идут в Qdrant синхронно, мимо embedding-service.
"""

from dataclasses import dataclass

from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import ProductId
from indexing_service.domain.value_objects.job_status import IndexAction
from indexing_service.domain.value_objects.search_text import SearchText
from indexing_service.domain.value_objects.sku import Sku


@dataclass(frozen=True, slots=True)
class EmbeddingJobRequest:
    """Запрос на постановку задания эмбеддинга.

    Attributes:
        product_id: Идентификатор товара.
        sku: Артикул.
        aggregate_version: Версия агрегата товара на момент события.
        content_version: Версия текста, на которой считаются векторы (§9.4).
        content_hash: Хэш текста — водяной знак дедупликации.
        text: Готовый текст документа (до чанкинга).
        action: Тип индексации (полная или ре-эмбеддинг).
        target_collection: Целевая коллекция для reindex (иначе ``None``).
    """

    product_id: ProductId
    sku: Sku
    aggregate_version: int
    content_version: int
    content_hash: ContentHash
    text: SearchText
    action: IndexAction
    target_collection: str | None = None
