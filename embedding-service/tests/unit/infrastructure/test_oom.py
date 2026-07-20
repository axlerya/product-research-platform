"""Unit-тесты split_retry — OOM-guard с дроблением батча (§8.5)."""

import pytest

from embedding_service.infrastructure.embedding.oom import split_retry


class _FakeOOM(Exception):
    """Имитация torch.cuda.OutOfMemoryError."""


def test_passthrough_without_oom_types() -> None:
    calls: list[list[str]] = []

    def encode(batch: list[str]) -> list[str]:
        calls.append(list(batch))
        return [x.upper() for x in batch]

    out = split_retry(encode, ["a", "b"], oom_types=(), on_oom=lambda: None)
    assert out == ["A", "B"]
    assert calls == [["a", "b"]]


def test_splits_on_oom_and_preserves_order() -> None:
    empties: list[int] = []

    def encode(batch: list[str]) -> list[str]:
        if len(batch) > 1:
            raise _FakeOOM
        return [batch[0].upper()]

    out = split_retry(
        encode,
        ["a", "b", "c"],
        oom_types=(_FakeOOM,),
        on_oom=lambda: empties.append(1),
    )
    assert out == ["A", "B", "C"]
    assert len(empties) >= 1  # empty_cache вызывался


def test_persistent_oom_on_single_reraises() -> None:
    def encode(batch: list[str]) -> list[str]:
        raise _FakeOOM

    with pytest.raises(_FakeOOM):
        split_retry(encode, ["a"], oom_types=(_FakeOOM,), on_oom=lambda: None)
