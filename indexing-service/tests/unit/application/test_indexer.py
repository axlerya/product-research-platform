"""Тесты разделяемых операций индексации (tombstone)."""

from datetime import UTC, datetime
from uuid import UUID

from indexing_service.application.indexer import tombstone
from indexing_service.domain.value_objects.identifiers import ProductId
from tests.support.fakes import FakeVectorIndex, FixedClock

NOW = datetime(2026, 7, 19, 10, 15, 30, tzinfo=UTC)
PID = ProductId(UUID(int=1))


async def test_tombstone_marks_deleted_and_keeps_version():
    index = FakeVectorIndex()
    index.preload(
        PID,
        {
            "aggregate_version": 5,
            "model_version": "m",
            "indexed_at": NOW.isoformat(),
            "content_hash": None,
        },
    )
    await tombstone(PID, index=index, clock=FixedClock(NOW), version=8)
    payload = index.payload_of(PID)
    assert payload["is_deleted"] is True
    assert payload["aggregate_version"] == 8
