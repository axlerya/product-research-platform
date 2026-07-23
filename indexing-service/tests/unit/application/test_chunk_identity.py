"""Тесты детерминированных идентификаторов под-чанков (§9.1)."""

from uuid import UUID

import pytest

from indexing_service.application.chunk_identity import subchunk_point_id

_PARENT = "11111111-1111-1111-1111-111111111111"


def test_zero_subchunk_reuses_parent_point():
    assert subchunk_point_id(_PARENT, 0) == _PARENT


def test_other_subchunks_get_derived_uuid():
    point_id = subchunk_point_id(_PARENT, 1)
    assert point_id != _PARENT
    UUID(point_id)  # валидный UUID — Qdrant принимает только такие id


def test_is_deterministic():
    assert subchunk_point_id(_PARENT, 2) == subchunk_point_id(_PARENT, 2)


def test_different_indexes_differ():
    ids = {subchunk_point_id(_PARENT, i) for i in range(4)}
    assert len(ids) == 4


def test_different_parents_differ():
    other = "22222222-2222-2222-2222-222222222222"
    assert subchunk_point_id(_PARENT, 1) != subchunk_point_id(other, 1)


def test_rejects_negative_index():
    with pytest.raises(ValueError):
        subchunk_point_id(_PARENT, -1)
