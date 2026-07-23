"""Тесты сущности ``IndexingJob``."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from indexing_service.domain.entities.indexing_job import Chunk, IndexingJob
from indexing_service.domain.exceptions import InvalidJobError
from indexing_service.domain.value_objects.content_hash import ContentHash
from indexing_service.domain.value_objects.identifiers import JobId, ProductId
from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    IndexAction,
    JobStatus,
)
from indexing_service.domain.value_objects.sku import Sku

NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _chunk(ix: int = 0, text_id: str = "t0", point_id: str = "p0") -> Chunk:
    return Chunk(
        chunk_ix=ix,
        text_id=text_id,
        point_id=point_id,
        status=ChunkStatus.PENDING,
        attempts=0,
    )


def _job(**over) -> IndexingJob:
    fields = dict(
        job_id=JobId(UUID(int=1)),
        product_id=ProductId(UUID(int=2)),
        sku=Sku("PROD-001"),
        aggregate_version=1,
        content_version=1,
        content_hash=ContentHash.of("x"),
        action=IndexAction.FULL_INDEX,
        target_collection=None,
        expected_model=None,
        status=JobStatus.PENDING,
        chunks=(_chunk(),),
        created_at=NOW,
        updated_at=NOW,
        applied_at=None,
    )
    fields.update(over)
    return IndexingJob(**fields)


def test_valid_job():
    job = _job()
    assert job.status is JobStatus.PENDING
    assert len(job.chunks) == 1


def test_rejects_version_below_one():
    with pytest.raises(InvalidJobError):
        _job(aggregate_version=0)


def test_rejects_content_version_below_one():
    with pytest.raises(InvalidJobError):
        _job(content_version=0)


def test_rejects_empty_chunks():
    with pytest.raises(InvalidJobError):
        _job(chunks=())


def test_rejects_duplicate_text_ids():
    with pytest.raises(InvalidJobError):
        _job(chunks=(_chunk(0, "t", "p0"), _chunk(1, "t", "p1")))


def test_rejects_empty_chunk_text_id():
    with pytest.raises(InvalidJobError):
        _chunk(text_id="")


def test_rechunk_replaces_in_place_keeping_order():
    job = _job(
        chunks=(
            _chunk(0, "t0", "p0"),
            _chunk(1, "t1", "p1"),
            _chunk(2, "t2", "p2"),
        )
    )

    rechunked = job.rechunk(
        "t1", [_chunk(1, "t1a", "p1a"), _chunk(3, "t1b", "p1b")]
    )

    assert [c.text_id for c in rechunked.chunks] == [
        "t0",
        "t1a",
        "t1b",
        "t2",
    ]


def test_rechunk_rejects_empty_replacement():
    with pytest.raises(InvalidJobError):
        _job().rechunk("t0", [])


def test_rechunk_rejects_unknown_text_id():
    with pytest.raises(InvalidJobError):
        _job().rechunk("нет-такого", [_chunk(1, "t1", "p1")])


def test_rechunk_rejects_duplicate_text_ids():
    job = _job(chunks=(_chunk(0, "t0", "p0"), _chunk(1, "t1", "p1")))
    with pytest.raises(InvalidJobError):
        job.rechunk("t0", [_chunk(0, "t1", "pX")])
