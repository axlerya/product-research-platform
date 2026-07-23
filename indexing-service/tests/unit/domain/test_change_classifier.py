"""Тесты доменной классификации изменений (§1.4, §6.2).

Проверяют строгий guard по версии, композицию сиблингов одной версии,
gap-repair, дедуп ре-эмбеддинга по content_hash и защиту от воскрешения.
"""

from datetime import UTC, datetime

from indexing_service.domain.services.change_classifier import (
    ChangeKind,
    IndexingAction,
    classify,
)
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.watermark import IndexingWatermark

_NOW = datetime(2026, 7, 19, tzinfo=UTC)
_MODEL = "BAAI/bge-m3@rev|pool=cls|norm=1|dim=1024"
_HASH = ContentHash.of("текст")


def _wm(version=5, model=_MODEL, content_hash=_HASH):
    return IndexingWatermark(
        aggregate_version=version,
        model_version=model,
        content_hash=content_hash,
        indexed_at=_NOW,
    )


# --- created ---
def test_created_new_point_full_index():
    assert classify(ChangeKind.CREATED, 1, None) is IndexingAction.FULL_INDEX


def test_created_redelivery_same_version_reapplies():
    action = classify(ChangeKind.CREATED, 5, _wm(5))
    assert action is IndexingAction.FULL_INDEX


def test_created_stale_skipped():
    assert classify(ChangeKind.CREATED, 4, _wm(5)) is IndexingAction.SKIP


# --- deleted ---
def test_deleted_existing_tombstones():
    action = classify(ChangeKind.DELETED, 6, _wm(5))
    assert action is IndexingAction.TOMBSTONE


def test_deleted_missing_point_skipped():
    assert classify(ChangeKind.DELETED, 6, None) is IndexingAction.SKIP


def test_deleted_stale_skipped():
    assert classify(ChangeKind.DELETED, 4, _wm(5)) is IndexingAction.SKIP


# --- commercial_data_changed ---
def test_commercial_payload_only():
    action = classify(ChangeKind.COMMERCIAL_CHANGED, 6, _wm(5))
    assert action is IndexingAction.PAYLOAD_ONLY


def test_commercial_missing_point_repairs():
    action = classify(ChangeKind.COMMERCIAL_CHANGED, 6, None)
    assert action is IndexingAction.REPAIR


def test_commercial_stale_skipped():
    action = classify(ChangeKind.COMMERCIAL_CHANGED, 4, _wm(5))
    assert action is IndexingAction.SKIP


# --- content_changed ---
def test_content_missing_point_repairs():
    action = classify(ChangeKind.CONTENT_CHANGED, 6, None)
    assert action is IndexingAction.REPAIR


def test_content_changed_text_reembeds():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5),
        content_hash=ContentHash.of("другое"),
        current_model=_MODEL,
    )
    assert action is IndexingAction.REEMBED


def test_content_unchanged_text_same_model_skips_reembed():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5, content_hash=_HASH),
        content_hash=_HASH,
        current_model=_MODEL,
    )
    assert action is IndexingAction.PAYLOAD_ONLY


def test_content_same_text_different_model_reembeds():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5, model="old@x"),
        content_hash=_HASH,
        current_model=_MODEL,
    )
    assert action is IndexingAction.REEMBED


def test_content_same_text_without_pinned_model_skips_reembed():
    """Модель не закреплена — сверять не с чем, хватает совпадения текста."""
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5, content_hash=_HASH, model="что-угодно"),
        content_hash=_HASH,
        current_model=None,
    )
    assert action is IndexingAction.PAYLOAD_ONLY


def test_content_new_text_without_pinned_model_reembeds():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5, content_hash=_HASH),
        content_hash=ContentHash.of("новое"),
        current_model=None,
    )
    assert action is IndexingAction.REEMBED


def test_content_not_yet_embedded_reembeds():
    """Векторов ещё нет (нет content_hash в знаке) → ставим задание."""
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        6,
        _wm(5, content_hash=None),
        content_hash=_HASH,
        current_model=None,
    )
    assert action is IndexingAction.REEMBED


def test_content_stale_skipped():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        4,
        _wm(5),
        content_hash=_HASH,
        current_model=_MODEL,
    )
    assert action is IndexingAction.SKIP


# --- сиблинги одной версии (§6.2) ---
def test_same_version_siblings_both_apply():
    # Хранимый водяной знак несёт СТАРЫЙ hash (_HASH); входящий content
    # меняет текст (fresh) → оба сиблинга версии 5 применяются.
    fresh = ContentHash.of("новое")
    commercial = classify(ChangeKind.COMMERCIAL_CHANGED, 5, _wm(5))
    content = classify(
        ChangeKind.CONTENT_CHANGED,
        5,
        _wm(5),
        content_hash=fresh,
        current_model=_MODEL,
    )
    assert commercial is IndexingAction.PAYLOAD_ONLY
    assert content is IndexingAction.REEMBED


# --- защита от воскрешения (§6.5) ---
def test_late_content_after_tombstone_skipped():
    action = classify(
        ChangeKind.CONTENT_CHANGED,
        7,
        _wm(version=8),
        content_hash=ContentHash.of("x"),
        current_model=_MODEL,
    )
    assert action is IndexingAction.SKIP
