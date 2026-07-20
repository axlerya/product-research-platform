"""Тесты доменных enum'ов jobs/requests."""

from indexing_service.domain.value_objects.job_status import (
    ChunkStatus,
    EmbeddingErrorCode,
    IndexAction,
    JobStatus,
    RequestStatus,
)


def test_job_status_values():
    assert JobStatus.PENDING == "pending"
    assert set(JobStatus) == {
        JobStatus.PENDING,
        JobStatus.AWAITING,
        JobStatus.PARTIALLY_FAILED,
        JobStatus.DONE,
        JobStatus.FAILED,
    }


def test_error_codes_match_embedding_service():
    assert {code.value for code in EmbeddingErrorCode} == {
        "EMPTY_TEXT",
        "TEXT_TOO_LONG",
        "TOKENS_EXCEEDED",
        "INFERENCE_FAILED",
    }


def test_index_action_values():
    assert IndexAction.FULL_INDEX == "full_index"
    assert IndexAction.REEMBED == "reembed"


def test_request_and_chunk_status():
    assert RequestStatus.AWAITING == "awaiting"
    assert ChunkStatus.OK == "ok"
