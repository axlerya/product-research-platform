"""Unit-тесты портов application: структурная сообразность фейков.

Порты — Protocol (структурная типизация). Проверяем, что реализация-фейк
удовлетворяет форме порта и что EmbeddingProvider не тянет фреймворки.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from embedding_service.application.dto import ProviderStatus
from embedding_service.application.ports.clock import Clock
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.application.ports.id_generator import IdGenerator
from embedding_service.application.ports.tokenizer import Tokenizer
from embedding_service.domain.value_objects.dense_vector import DenseVector
from embedding_service.domain.value_objects.embedding import Embedding
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.sparse_vector import SparseVector
from embedding_service.domain.value_objects.token_count import TokenCount

_MODEL = EmbeddingModelId(
    name="BAAI/bge-m3",
    revision="unknown",
    pooling="cls",
    normalized=True,
    dim=2,
)


class _FakeProvider:
    @property
    def model_id(self) -> EmbeddingModelId:
        return _MODEL

    async def embed(
        self, texts: Sequence[EmbeddingText], *, kind: EmbeddingKind
    ) -> list[Embedding]:
        return [
            Embedding(
                dense=DenseVector((0.1, 0.2)),
                sparse=SparseVector((1,), (0.5,)),
                model_id=_MODEL,
            )
            for _ in texts
        ]

    async def warmup(self) -> None:
        return None

    async def probe(self) -> ProviderStatus:
        return ProviderStatus(
            loaded=True,
            device="cpu",
            precision="fp32",
            degraded=False,
            model_key=_MODEL.key,
        )


class _FakeTokenizer:
    def count_tokens(self, text: EmbeddingText) -> TokenCount:
        return TokenCount(len(text.value.split()))

    def truncate(
        self, text: EmbeddingText, max_tokens: int
    ) -> tuple[EmbeddingText, TokenCount, bool]:
        return text, self.count_tokens(text), False


class _FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 20, tzinfo=UTC)


class _FakeIds:
    def new_uuid7(self) -> UUID:
        return uuid4()


def _use_provider(provider: EmbeddingProvider) -> EmbeddingModelId:
    return provider.model_id


def _use_tokenizer(tokenizer: Tokenizer, text: EmbeddingText) -> TokenCount:
    return tokenizer.count_tokens(text)


def _use_clock(clock: Clock) -> datetime:
    return clock.now()


def _use_ids(ids: IdGenerator) -> UUID:
    return ids.new_uuid7()


async def test_fake_provider_conforms() -> None:
    provider: EmbeddingProvider = _FakeProvider()
    assert _use_provider(provider) == _MODEL
    out = await provider.embed(
        [EmbeddingText("a"), EmbeddingText("b")], kind=EmbeddingKind.QUERY
    )
    assert len(out) == 2
    assert (await provider.probe()).loaded
    await provider.warmup()


def test_fake_tokenizer_conforms() -> None:
    tok: Tokenizer = _FakeTokenizer()
    assert _use_tokenizer(tok, EmbeddingText("two words")) == TokenCount(2)
    _, count, truncated = tok.truncate(EmbeddingText("x"), 10)
    assert count == TokenCount(1)
    assert truncated is False


def test_fake_clock_and_ids_conform() -> None:
    assert _use_clock(_FakeClock()).tzinfo is UTC
    assert isinstance(_use_ids(_FakeIds()), UUID)
