"""``BgeM3EmbeddingProvider`` — реализация порта через локальную BGE-M3.

FlagEmbedding/torch импортируются только в этом модуле (ленивая проводка в
``load_bge_m3_provider``). Блокирующий ``encode`` уносится в executor;
конвертация тестируется на fake-энкодере без загрузки весов.
"""

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import Executor
from typing import Any, Protocol

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.exceptions import (
    InferenceError,
    ProbeFailed,
)
from embedding_service.domain.exceptions import InvalidVectorError
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.infrastructure.embedding.device import (
    resolve_device,
    resolve_precision,
)
from embedding_service.infrastructure.embedding.oom import split_retry
from embedding_service.infrastructure.embedding.sparse import (
    lexical_weights_to_sparse,
)

_PROBE_TEXT = "warmup probe: проверка загрузки и формы эмбеддинга"
# Пара (dense-строка, lexical-weights) одного текста от энкодера.
_Row = tuple[Any, Any]


def _noop() -> None:
    return None


class Bgem3Encoder(Protocol):
    """Утиный тип ``FlagEmbedding.BGEM3FlagModel``."""

    def encode(self, sentences: list[str], **kwargs: Any) -> dict[str, Any]:
        """Возвращает ``{"dense_vecs", "lexical_weights"}``."""
        ...


class BgeM3EmbeddingProvider:
    """Строит dense + sparse эмбеддинги локальной BGE-M3."""

    def __init__(
        self,
        encoder: Bgem3Encoder,
        *,
        model_id: EmbeddingModelId,
        executor: Executor | None = None,
        device: str = "cpu",
        precision: str = "fp32",
        max_length: int = 8192,
        batch_size: int = 16,
        oom_types: tuple[type[BaseException], ...] = (),
        empty_cache: Callable[[], None] | None = None,
    ) -> None:
        self._encoder = encoder
        self._model_id = model_id
        self._executor = executor
        self._device = device
        self._precision = precision
        self._max_length = max_length
        self._batch_size = batch_size
        self._oom_types = oom_types
        self._empty_cache = empty_cache or _noop

    @property
    def model_id(self) -> EmbeddingModelId:
        return self._model_id

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        raw = [text.value for text in texts]
        if not raw:
            return []
        rows = await self._run(raw)
        return [
            Embedding(
                dense=DenseVector(tuple(float(x) for x in dense)),
                sparse=lexical_weights_to_sparse(weights),
                model_id=self._model_id,
            )
            for dense, weights in rows
        ]

    async def _run(self, raw: list[str]) -> list[_Row]:
        if self._executor is None:
            return await asyncio.to_thread(self._encode, raw)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._encode, raw)

    def _encode(self, raw: list[str]) -> list[_Row]:
        try:
            return split_retry(
                self._encode_once,
                raw,
                oom_types=self._oom_types,
                on_oom=self._empty_cache,
            )
        except Exception as exc:  # включая CUDA OOM после исчерпания split
            raise InferenceError(str(exc)) from exc

    def _encode_once(self, raw: list[str]) -> list[_Row]:
        output = self._encoder.encode(
            raw,
            return_dense=True,
            return_sparse=True,
            max_length=self._max_length,
            batch_size=self._batch_size,
        )
        dense = output["dense_vecs"]
        weights = output["lexical_weights"]
        return [(dense[i], weights[i]) for i in range(len(raw))]

    async def warmup(self) -> None:
        try:
            embeddings = await self.embed(
                [EmbeddingText(_PROBE_TEXT)], kind=EmbeddingKind.QUERY
            )
        except (InvalidVectorError, InferenceError) as exc:
            raise ProbeFailed(f"probe: {exc}") from exc
        if not embeddings[0].sparse.values:
            raise ProbeFailed(
                "probe: пустой sparse (return_sparse не сработал)"
            )

    async def probe(self) -> ProviderStatus:
        return ProviderStatus(
            loaded=True,
            device=self._device,
            precision=self._precision,
            degraded=False,
            model_key=self._model_id.key,
        )


def load_bge_m3_provider(  # pragma: no cover - тяжёлая проводка (e2e/GPU)
    *,
    model: str = "BAAI/bge-m3",
    revision: str = "",
    device: str = "auto",
    precision: str = "fp16",
    dim: int = 1024,
    pooling: str = "cls",
    normalized: bool = True,
) -> BgeM3EmbeddingProvider:
    """Загружает реальную BGE-M3 (lazy-импорт FlagEmbedding/torch)."""
    from concurrent.futures import ThreadPoolExecutor

    import torch
    from FlagEmbedding import BGEM3FlagModel

    resolved_device = resolve_device(device)
    resolved_precision = resolve_precision(precision, resolved_device)
    encoder = BGEM3FlagModel(
        model,
        revision=revision or None,
        use_fp16=resolved_precision != "fp32",
        devices=resolved_device,
    )
    model_id = EmbeddingModelId(
        name=model,
        revision=revision or "unknown",
        pooling=pooling,
        normalized=normalized,
        dim=dim,
    )
    oom_types: tuple[type[BaseException], ...] = ()
    empty_cache: Callable[[], None] = _noop
    if resolved_device == "cuda":
        oom_types = (torch.cuda.OutOfMemoryError,)
        empty_cache = torch.cuda.empty_cache
    return BgeM3EmbeddingProvider(
        encoder,
        model_id=model_id,
        executor=ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="bge-encode"
        ),
        device=resolved_device,
        precision=resolved_precision,
        oom_types=oom_types,
        empty_cache=empty_cache,
    )
