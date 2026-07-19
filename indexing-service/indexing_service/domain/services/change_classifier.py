"""Доменная классификация изменений каталога (§1.4, §6.2).

Единственный источник истины маршрутизации события в действие над Qdrant.
Реализует строгий guard по версии (пропуск только строго перекрытого),
gap-repair отсутствующей точки, дедуп ре-эмбеддинга по ``content_hash`` и
защиту от воскрешения (tombstone сохраняет версию).
"""

from enum import StrEnum

from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.watermark import IndexingWatermark


class ChangeKind(StrEnum):
    """Вид изменения товара (доменное соответствие 4 типам событий)."""

    CREATED = "created"
    CONTENT_CHANGED = "content_changed"
    COMMERCIAL_CHANGED = "commercial_changed"
    DELETED = "deleted"


class IndexingAction(StrEnum):
    """Действие над коллекцией Qdrant, выбранное классификацией."""

    FULL_INDEX = "full_index"
    REEMBED = "reembed"
    PAYLOAD_ONLY = "payload_only"
    TOMBSTONE = "tombstone"
    REPAIR = "repair"
    SKIP = "skip"


def classify(
    kind: ChangeKind,
    event_version: int,
    watermark: IndexingWatermark | None,
    *,
    content_hash: ContentHash | None = None,
    current_model: str | None = None,
) -> IndexingAction:
    """Выбирает действие по виду изменения и водяному знаку точки.

    Args:
        kind: Вид изменения.
        event_version: ``aggregate_version`` события.
        watermark: Текущий водяной знак точки (``None``, если точки нет).
        content_hash: Хэш нового текста (для дедупа ре-эмбеддинга).
        current_model: Ключ текущей модели эмбеддингов.

    Returns:
        Действие ``IndexingAction``.
    """
    # Строгий guard: пропускаем только СТРОГО перекрытое более новой версией.
    # События одной версии (сиблинги одной команды) не отбрасываются.
    if watermark is not None and event_version < watermark.aggregate_version:
        return IndexingAction.SKIP

    if kind is ChangeKind.CREATED:
        return IndexingAction.FULL_INDEX

    if kind is ChangeKind.DELETED:
        if watermark is None:
            # Никогда не индексировали — удалять нечего.
            return IndexingAction.SKIP
        return IndexingAction.TOMBSTONE

    # Частичные события: точки ещё нет → восстанавливаем из catalog.
    if watermark is None:
        return IndexingAction.REPAIR

    if kind is ChangeKind.COMMERCIAL_CHANGED:
        return IndexingAction.PAYLOAD_ONLY

    # CONTENT_CHANGED: пропускаем ре-эмбеддинг, если и текст, и модель те же.
    if (
        content_hash is not None
        and current_model is not None
        and watermark.content_hash == content_hash
        and watermark.model_version == current_model
    ):
        return IndexingAction.PAYLOAD_ONLY
    return IndexingAction.REEMBED
