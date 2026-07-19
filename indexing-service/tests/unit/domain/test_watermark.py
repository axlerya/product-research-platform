"""Тесты value object ``IndexingWatermark`` — водяной знак индексации."""

from datetime import UTC, datetime

import pytest

from indexing_service.domain.exceptions import InvalidWatermarkError
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.watermark import IndexingWatermark

_NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)


def test_holds_fields():
    watermark = IndexingWatermark(
        aggregate_version=6,
        model_version="BAAI/bge-m3@rev|pool=cls|norm=1|dim=1024",
        content_hash=ContentHash.of("x"),
        indexed_at=_NOW,
    )
    assert watermark.aggregate_version == 6
    assert watermark.model_version.endswith("dim=1024")


def test_content_hash_optional():
    watermark = IndexingWatermark(
        aggregate_version=1,
        model_version="m",
        content_hash=None,
        indexed_at=_NOW,
    )
    assert watermark.content_hash is None


def test_rejects_version_below_one():
    with pytest.raises(InvalidWatermarkError):
        IndexingWatermark(
            aggregate_version=0,
            model_version="m",
            content_hash=None,
            indexed_at=_NOW,
        )
