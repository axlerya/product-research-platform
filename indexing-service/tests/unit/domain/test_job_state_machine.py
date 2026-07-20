"""Тесты доменной машины состояний ``IndexingJob`` (§8)."""

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

_NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _job(*statuses: ChunkStatus) -> IndexingJob:
    chunks = tuple(
        Chunk(
            chunk_ix=index,
            text_id=f"c{index}",
            point_id=f"p{index}",
            status=status,
            attempts=0,
        )
        for index, status in enumerate(statuses)
    )
    return IndexingJob(
        job_id=JobId(UUID(int=1)),
        product_id=ProductId(UUID(int=2)),
        sku=Sku("PROD-1"),
        aggregate_version=1,
        content_version=1,
        content_hash=ContentHash.of("t"),
        action=IndexAction.FULL_INDEX,
        target_collection=None,
        expected_model=None,
        status=JobStatus.AWAITING,
        chunks=chunks,
        created_at=_NOW,
        updated_at=_NOW,
        applied_at=None,
    )


def test_chunk_transitions():
    chunk = Chunk(
        chunk_ix=0,
        text_id="c0",
        point_id="p0",
        status=ChunkStatus.PENDING,
        attempts=0,
    )
    assert chunk.mark_ok().status is ChunkStatus.OK
    retrying = chunk.mark_retrying()
    assert retrying.status is ChunkStatus.RETRYING
    assert retrying.attempts == 1
    assert chunk.mark_failed().status is ChunkStatus.FAILED


def test_chunk_by_text_id_found_and_missing():
    job = _job(ChunkStatus.PENDING)
    assert job.chunk_by_text_id("c0").point_id == "p0"
    with pytest.raises(InvalidJobError):
        job.chunk_by_text_id("nope")


def test_mark_chunk_ok_replaces_only_that_chunk():
    job = _job(ChunkStatus.PENDING, ChunkStatus.PENDING)
    updated = job.mark_chunk_ok("c1")
    assert updated.chunk_by_text_id("c1").status is ChunkStatus.OK
    assert updated.chunk_by_text_id("c0").status is ChunkStatus.PENDING
    # исходный job не мутирован (frozen)
    assert job.chunk_by_text_id("c1").status is ChunkStatus.PENDING


def test_mark_chunk_unknown_raises():
    job = _job(ChunkStatus.PENDING)
    with pytest.raises(InvalidJobError):
        job.mark_chunk_ok("missing")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((ChunkStatus.PENDING, ChunkStatus.PENDING), JobStatus.AWAITING),
        ((ChunkStatus.OK, ChunkStatus.PENDING), JobStatus.AWAITING),
        ((ChunkStatus.OK, ChunkStatus.OK), JobStatus.DONE),
        (
            (ChunkStatus.RETRYING, ChunkStatus.PENDING),
            JobStatus.PARTIALLY_FAILED,
        ),
        (
            (ChunkStatus.FAILED, ChunkStatus.PENDING),
            JobStatus.PARTIALLY_FAILED,
        ),
        ((ChunkStatus.OK, ChunkStatus.FAILED), JobStatus.FAILED),
        ((ChunkStatus.FAILED, ChunkStatus.FAILED), JobStatus.FAILED),
    ],
)
def test_recompute_status(statuses, expected):
    assert _job(*statuses).recompute_status().status is expected


def test_is_terminal():
    assert _job(ChunkStatus.OK).recompute_status().is_terminal
    assert _job(ChunkStatus.FAILED).recompute_status().is_terminal
    assert not _job(ChunkStatus.PENDING).recompute_status().is_terminal


def test_full_lifecycle_awaiting_to_done():
    job = _job(ChunkStatus.PENDING, ChunkStatus.PENDING)
    job = job.mark_chunk_ok("c0").recompute_status()
    assert job.status is JobStatus.AWAITING
    job = job.mark_chunk_ok("c1").recompute_status()
    assert job.status is JobStatus.DONE
