"""``BgeRerankerProvider`` — реализация порта через BAAI/bge-reranker-v2-m3.

FlagEmbedding/torch импортируются только здесь (ленивая проводка в
``load_bge_reranker_provider``). Блокирующий ``compute_score`` уносится в
executor; конвертация тестируется на fake-энкодере без загрузки весов.
"""

import asyncio
import math
from collections.abc import Callable, Sequence
from concurrent.futures import Executor
from typing import Any, Protocol

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.exceptions import (
    InferenceError,
    ProbeFailed,
)
from embedding_service.domain.value_objects.reranking.reranker_model_id import (
    RerankerModelId,
)
from embedding_service.infrastructure.reranking.device import (
    resolve_device,
    resolve_precision,
)
from embedding_service.infrastructure.reranking.oom import split_retry

_PROBE_QUERY = "warmup probe"
_PROBE_DOC = "проверка загрузки reranker и формы скора"
# Пара [query, passage] для cross-encoder.
_Pair = list[str]


def _noop() -> None:
    return None


class FlagRerankerEncoder(Protocol):
    """Утиный тип ``FlagEmbedding.FlagReranker``."""

    def compute_score(self, sentence_pairs: list[_Pair], **kwargs: Any) -> Any:
        """Скор(ы) релевантности для пар ``[query, passage]``."""
        ...


class BgeRerankerProvider:
    """Скорит релевантность документов запросу локальной bge-reranker-v2-m3."""

    def __init__(
        self,
        encoder: FlagRerankerEncoder,
        *,
        model_id: RerankerModelId,
        executor: Executor | None = None,
        device: str = "cpu",
        precision: str = "fp32",
        normalize: bool = True,
        oom_types: tuple[type[BaseException], ...] = (),
        empty_cache: Callable[[], None] | None = None,
    ) -> None:
        self._encoder = encoder
        self._model_id = model_id
        self._executor = executor
        self._device = device
        self._precision = precision
        self._normalize = normalize
        self._oom_types = oom_types
        self._empty_cache = empty_cache or _noop

    @property
    def model_id(self) -> RerankerModelId:
        return self._model_id

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        pairs: list[_Pair] = [[query, doc] for doc in documents]
        return await self._run(pairs)

    async def _run(self, pairs: list[_Pair]) -> list[float]:
        if self._executor is None:
            return await asyncio.to_thread(self._compute, pairs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._compute, pairs)

    def _compute(self, pairs: list[_Pair]) -> list[float]:
        try:
            return split_retry(
                self._compute_once,
                pairs,
                oom_types=self._oom_types,
                on_oom=self._empty_cache,
            )
        except Exception as exc:  # включая CUDA OOM после исчерпания split
            raise InferenceError(str(exc)) from exc

    def _compute_once(self, pairs: list[_Pair]) -> list[float]:
        raw = self._encoder.compute_score(pairs, normalize=self._normalize)
        if isinstance(raw, int | float):
            return [float(raw)]
        return [float(score) for score in raw]

    async def warmup(self) -> None:
        try:
            scores = await self.rerank(_PROBE_QUERY, [_PROBE_DOC])
        except InferenceError as exc:
            raise ProbeFailed(f"probe: {exc}") from exc
        if len(scores) != 1 or not math.isfinite(scores[0]):
            raise ProbeFailed("probe: некорректная форма скора reranker")

    async def probe(self) -> ProviderStatus:
        return ProviderStatus(
            loaded=True,
            device=self._device,
            precision=self._precision,
            degraded=False,
            model_key=self._model_id.key,
        )

    async def aclose(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)


def load_bge_reranker_provider(  # pragma: no cover - тяжёлая проводка (e2e/GPU)
    *,
    model: str = "BAAI/bge-reranker-v2-m3",
    revision: str = "",
    device: str = "auto",
    precision: str = "fp16",
    normalized: bool = True,
    query_max_length: int = 256,
    passage_max_length: int = 512,
) -> BgeRerankerProvider:
    """Загружает реальную bge-reranker-v2-m3 (lazy FlagEmbedding/torch)."""
    from concurrent.futures import ThreadPoolExecutor

    import torch
    from FlagEmbedding import FlagReranker

    resolved_device = resolve_device(device)
    resolved_precision = resolve_precision(precision, resolved_device)
    encoder = FlagReranker(
        model,
        use_fp16=resolved_precision != "fp32",
        devices=resolved_device,
        query_max_length=query_max_length,
        passage_max_length=passage_max_length,
    )
    model_id = RerankerModelId(
        name=model,
        revision=revision or "unknown",
        normalized=normalized,
    )
    oom_types: tuple[type[BaseException], ...] = ()
    empty_cache: Callable[[], None] = _noop
    if resolved_device == "cuda":
        oom_types = (torch.cuda.OutOfMemoryError,)
        empty_cache = torch.cuda.empty_cache
    return BgeRerankerProvider(
        encoder,
        model_id=model_id,
        executor=ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="bge-reranker"
        ),
        device=resolved_device,
        precision=resolved_precision,
        normalize=normalized,
        oom_types=oom_types,
        empty_cache=empty_cache,
    )
