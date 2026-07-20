"""Unit-тесты ``BgeRerankerProvider`` на fake-энкодере (без torch/весов).

Проверяется построение пар (query, doc), передача normalize, выравнивание
скоров, обработка скалярного результата, OOM split-retry, маппинг ошибок и
warmup-probe.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from embedding_service.application.exceptions import InferenceError, ProbeFailed
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)
from embedding_service.infrastructure.reranking.bge_reranker import (
    BgeRerankerProvider,
)

_MODEL_ID = RerankerModelId(
    name="BAAI/bge-reranker-v2-m3", revision="unknown", normalized=True
)


class _FakeReranker:
    """Fake FlagReranker: скор = длина passage; опц. OOM на больших батчах."""

    def __init__(self, *, oom_over: int | None = None) -> None:
        self.calls: list[tuple[list[list[str]], dict[str, Any]]] = []
        self._oom_over = oom_over

    def compute_score(
        self, sentence_pairs: list[list[str]], **kwargs: Any
    ) -> list[float]:
        self.calls.append((list(sentence_pairs), kwargs))
        if self._oom_over is not None and len(sentence_pairs) > self._oom_over:
            raise _FakeOom
        return [float(len(pair[1])) for pair in sentence_pairs]


class _FakeOom(Exception):
    pass


def _provider(encoder: Any, **kwargs: Any) -> BgeRerankerProvider:
    return BgeRerankerProvider(encoder, model_id=_MODEL_ID, **kwargs)


class TestBgeReranker:
    async def test_builds_query_doc_pairs(self) -> None:
        encoder = _FakeReranker()
        await _provider(encoder).rerank("q", ["aa", "b"])
        assert encoder.calls[0][0] == [["q", "aa"], ["q", "b"]]

    async def test_passes_normalize_flag(self) -> None:
        encoder = _FakeReranker()
        await _provider(encoder, normalize=True).rerank("q", ["d"])
        assert encoder.calls[0][1].get("normalize") is True

    async def test_scores_aligned_to_documents(self) -> None:
        scores = await _provider(_FakeReranker()).rerank("q", ["aa", "bbbb"])
        assert scores == [2.0, 4.0]

    async def test_scalar_result_wrapped(self) -> None:
        class _Scalar:
            def compute_score(
                self, sentence_pairs: list[list[str]], **kwargs: Any
            ) -> float:
                return 0.5

        assert await _provider(_Scalar()).rerank("q", ["d"]) == [0.5]

    async def test_oom_triggers_split_retry(self) -> None:
        encoder = _FakeReranker(oom_over=1)  # OOM, если батч > 1 пары
        # empty_cache по умолчанию (_noop) — тоже покрываем.
        provider = _provider(encoder, oom_types=(_FakeOom,))
        assert await provider.rerank("q", ["aa", "bbb"]) == [2.0, 3.0]

    async def test_empty_documents_returns_empty(self) -> None:
        assert await _provider(_FakeReranker()).rerank("q", []) == []

    async def test_runs_in_executor(self) -> None:
        with ThreadPoolExecutor(max_workers=1) as executor:
            provider = _provider(_FakeReranker(), executor=executor)
            assert await provider.rerank("q", ["aa"]) == [2.0]

    async def test_warmup_inference_error_raises_probe_failed(self) -> None:
        class _Boom:
            def compute_score(
                self, sentence_pairs: list[list[str]], **kwargs: Any
            ) -> list[float]:
                raise RuntimeError("boom")

        with pytest.raises(ProbeFailed):
            await _provider(_Boom()).warmup()

    async def test_aclose_shuts_down_executor(self) -> None:
        executor = ThreadPoolExecutor(max_workers=1)
        provider = _provider(_FakeReranker(), executor=executor)
        await provider.aclose()
        assert executor._shutdown  # executor остановлен

    async def test_aclose_without_executor_is_noop(self) -> None:
        # executor=None (дефолт) — aclose безопасен и ничего не закрывает.
        await _provider(_FakeReranker()).aclose()

    async def test_encoder_error_becomes_inference_error(self) -> None:
        class _Boom:
            def compute_score(
                self, sentence_pairs: list[list[str]], **kwargs: Any
            ) -> list[float]:
                raise RuntimeError("boom")

        with pytest.raises(InferenceError):
            await _provider(_Boom()).rerank("q", ["d"])

    async def test_warmup_ok(self) -> None:
        await _provider(_FakeReranker()).warmup()

    async def test_warmup_bad_shape_raises_probe_failed(self) -> None:
        class _Empty:
            def compute_score(
                self, sentence_pairs: list[list[str]], **kwargs: Any
            ) -> list[float]:
                return []

        with pytest.raises(ProbeFailed):
            await _provider(_Empty()).warmup()

    async def test_probe_reports_loaded(self) -> None:
        status = await _provider(_FakeReranker()).probe()
        assert status.loaded is True
        assert status.model_key.startswith("BAAI/bge-reranker-v2-m3")

    async def test_model_id(self) -> None:
        assert _provider(_FakeReranker()).model_id.key == _MODEL_ID.key
