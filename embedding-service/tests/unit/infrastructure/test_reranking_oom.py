"""Unit-тесты обобщённого split-retry reranker (OOM-guard, изолированно)."""

import pytest

from embedding_service.infrastructure.reranking.oom import split_retry


class _Oom(Exception):
    pass


def test_returns_result_without_oom() -> None:
    def encode(items: list[str]) -> list[int]:
        return [len(x) for x in items]

    assert split_retry(
        encode, ["a", "bb", "ccc"], oom_types=(), on_oom=lambda: None
    ) == [1, 2, 3]


def test_splits_on_oom_preserving_order() -> None:
    cleared: list[int] = []

    def encode(items: list[str]) -> list[str]:
        if len(items) > 1:
            raise _Oom
        return [items[0].upper()]

    out = split_retry(
        encode,
        ["a", "b", "c"],
        oom_types=(_Oom,),
        on_oom=lambda: cleared.append(1),
    )
    assert out == ["A", "B", "C"]
    assert cleared  # on_oom вызывался при дроблении


def test_reraises_when_single_item_ooms() -> None:
    def encode(items: list[str]) -> list[str]:
        raise _Oom

    with pytest.raises(_Oom):
        split_retry(encode, ["a"], oom_types=(_Oom,), on_oom=lambda: None)
