"""Unit-тесты use cases U1-U5 на фейках (без I/O).

Проверяем: порядок, партиал (документы), fail-fast (запросы), batch-poison,
токен-лимиты, отсутствие токенайзера, проброс транзиентных ошибок, warmup/probe.
"""

import pytest

from embedding_service.application.dto import (
    EmbedDocumentsCommand,
    EmbedQueriesQuery,
    EmbedQueryQuery,
    RawTextItem,
)
from embedding_service.application.exceptions import (
    InferenceError,
    ProbeFailed,
    ValidationError,
)
from embedding_service.application.use_cases.describe_model import DescribeModel
from embedding_service.application.use_cases.embed_documents import (
    EmbedDocuments,
)
from embedding_service.application.use_cases.embed_queries import EmbedQueries
from embedding_service.application.use_cases.embed_query import EmbedQuery
from embedding_service.application.use_cases.warmup_model import WarmupModel
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.item_error import (
    EmbeddingErrorCode,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from tests.support.fakes import FakeEmbeddingProvider, FakeTokenizer

DOC_LIMITS = EmbeddingLimits(
    max_texts=10, max_text_chars=100, max_tokens=1000, max_total_bytes=100_000
)
QUERY_LIMITS = EmbeddingLimits(
    max_texts=5, max_text_chars=50, max_tokens=1000, max_total_bytes=10_000
)


def _cmd(*items: tuple[str, str]) -> EmbedDocumentsCommand:
    return EmbedDocumentsCommand(
        request_id="req-1",
        items=tuple(RawTextItem(text_id=i, text=t) for i, t in items),
        return_dense=True,
        return_sparse=True,
    )


class TestEmbedDocuments:
    async def test_happy_preserves_order(self) -> None:
        provider = FakeEmbeddingProvider(dim=2)
        uc = EmbedDocuments(provider, DOC_LIMITS)
        result = await uc.handle(_cmd(("a", "aa"), ("b", "bbb"), ("c", "c")))
        assert result.request_id == "req-1"
        assert result.model_key == provider.model_id.key
        assert result.dim == 2
        assert [r.text_id.value for r in result.results] == ["a", "b", "c"]
        assert all(r.is_ok for r in result.results)
        # провайдер вызван один раз со всеми текстами, kind=DOCUMENT
        assert len(provider.embed_calls) == 1
        texts, kind = provider.embed_calls[0]
        assert texts == ["aa", "bbb", "c"]
        assert kind is EmbeddingKind.DOCUMENT

    async def test_partial_empty_text(self) -> None:
        provider = FakeEmbeddingProvider()
        uc = EmbedDocuments(provider, DOC_LIMITS)
        result = await uc.handle(_cmd(("a", "ok"), ("b", "   "), ("c", "ok2")))
        assert result.results[0].is_ok
        assert not result.results[1].is_ok
        assert result.results[1].error.code is EmbeddingErrorCode.EMPTY_TEXT
        assert result.results[2].is_ok
        # инференс только для валидных текстов
        assert provider.embed_calls[0][0] == ["ok", "ok2"]

    async def test_partial_text_too_long(self) -> None:
        provider = FakeEmbeddingProvider()
        uc = EmbedDocuments(provider, DOC_LIMITS)
        result = await uc.handle(_cmd(("a", "x" * 101), ("b", "ok")))
        assert result.results[0].error.code is EmbeddingErrorCode.TEXT_TOO_LONG
        assert result.results[1].is_ok

    async def test_partial_tokens_exceeded(self) -> None:
        provider = FakeEmbeddingProvider()
        tok = FakeTokenizer(counts={"toobig": 5000}, default=1)
        uc = EmbedDocuments(provider, DOC_LIMITS, tokenizer=tok)
        result = await uc.handle(_cmd(("a", "toobig"), ("b", "ok")))
        assert (
            result.results[0].error.code is EmbeddingErrorCode.TOKENS_EXCEEDED
        )
        assert result.results[1].is_ok
        assert result.results[1].token_count.value == 1

    async def test_token_count_zero_without_tokenizer(self) -> None:
        uc = EmbedDocuments(FakeEmbeddingProvider(), DOC_LIMITS)
        result = await uc.handle(_cmd(("a", "hi")))
        assert result.results[0].token_count.value == 0

    async def test_all_invalid_skips_inference(self) -> None:
        provider = FakeEmbeddingProvider()
        uc = EmbedDocuments(provider, DOC_LIMITS)
        result = await uc.handle(_cmd(("a", "  "), ("b", "\t")))
        assert not any(r.is_ok for r in result.results)
        assert provider.embed_calls == []  # инференс не запускался

    async def test_empty_batch_park(self) -> None:
        uc = EmbedDocuments(FakeEmbeddingProvider(), DOC_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(_cmd())

    async def test_too_many_texts_park(self) -> None:
        limits = EmbeddingLimits(
            max_texts=2,
            max_text_chars=100,
            max_tokens=1000,
            max_total_bytes=1000,
        )
        uc = EmbedDocuments(FakeEmbeddingProvider(), limits)
        with pytest.raises(ValidationError):
            await uc.handle(_cmd(("a", "x"), ("b", "y"), ("c", "z")))

    async def test_total_bytes_park(self) -> None:
        limits = EmbeddingLimits(
            max_texts=10, max_text_chars=100, max_tokens=1000, max_total_bytes=3
        )
        uc = EmbedDocuments(FakeEmbeddingProvider(), limits)
        with pytest.raises(ValidationError):
            await uc.handle(_cmd(("a", "abcd")))

    async def test_blank_text_id_park(self) -> None:
        uc = EmbedDocuments(FakeEmbeddingProvider(), DOC_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(_cmd(("   ", "ok")))

    async def test_transient_inference_error_propagates(self) -> None:
        provider = FakeEmbeddingProvider(embed_error=InferenceError("boom"))
        uc = EmbedDocuments(provider, DOC_LIMITS)
        with pytest.raises(InferenceError):
            await uc.handle(_cmd(("a", "ok")))


class TestEmbedQuery:
    async def test_happy(self) -> None:
        provider = FakeEmbeddingProvider()
        uc = EmbedQuery(provider, QUERY_LIMITS)
        result = await uc.handle(EmbedQueryQuery(text="hello", request_id="r"))
        assert result.is_ok
        assert provider.embed_calls[0][1] is EmbeddingKind.QUERY

    async def test_empty_text_fail_fast(self) -> None:
        uc = EmbedQuery(FakeEmbeddingProvider(), QUERY_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(EmbedQueryQuery(text="   ", request_id=None))

    async def test_too_long_fail_fast(self) -> None:
        uc = EmbedQuery(FakeEmbeddingProvider(), QUERY_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(EmbedQueryQuery(text="x" * 51, request_id=None))

    async def test_tokens_exceeded_fail_fast(self) -> None:
        tok = FakeTokenizer(counts={"big": 5000})
        uc = EmbedQuery(FakeEmbeddingProvider(), QUERY_LIMITS, tokenizer=tok)
        with pytest.raises(ValidationError):
            await uc.handle(EmbedQueryQuery(text="big", request_id=None))

    async def test_transient_propagates(self) -> None:
        provider = FakeEmbeddingProvider(embed_error=InferenceError("x"))
        uc = EmbedQuery(provider, QUERY_LIMITS)
        with pytest.raises(InferenceError):
            await uc.handle(EmbedQueryQuery(text="ok", request_id=None))

    async def test_with_tokenizer_within_limit(self) -> None:
        tok = FakeTokenizer(counts={"hello": 3})
        uc = EmbedQuery(FakeEmbeddingProvider(), QUERY_LIMITS, tokenizer=tok)
        result = await uc.handle(EmbedQueryQuery(text="hello", request_id=None))
        assert result.is_ok
        assert result.token_count.value == 3


class TestEmbedQueries:
    async def test_happy_order(self) -> None:
        provider = FakeEmbeddingProvider()
        uc = EmbedQueries(provider, QUERY_LIMITS)
        batch = await uc.handle(
            EmbedQueriesQuery(texts=("a", "bb", "ccc"), request_id="r")
        )
        assert batch.all_ok
        assert [i.text_id.value for i in batch.items] == ["0", "1", "2"]
        assert provider.embed_calls[0][1] is EmbeddingKind.QUERY

    async def test_empty_batch_fail_fast(self) -> None:
        uc = EmbedQueries(FakeEmbeddingProvider(), QUERY_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(EmbedQueriesQuery(texts=(), request_id=None))

    async def test_one_bad_fails_whole_call(self) -> None:
        uc = EmbedQueries(FakeEmbeddingProvider(), QUERY_LIMITS)
        with pytest.raises(ValidationError):
            await uc.handle(
                EmbedQueriesQuery(texts=("ok", "x" * 51), request_id=None)
            )

    async def test_with_tokenizer_within_limit(self) -> None:
        tok = FakeTokenizer(counts={"a": 2, "bb": 3})
        uc = EmbedQueries(FakeEmbeddingProvider(), QUERY_LIMITS, tokenizer=tok)
        batch = await uc.handle(
            EmbedQueriesQuery(texts=("a", "bb"), request_id=None)
        )
        assert [i.token_count.value for i in batch.items] == [2, 3]

    async def test_tokens_exceeded_fail_fast(self) -> None:
        tok = FakeTokenizer(counts={"big": 5000})
        uc = EmbedQueries(FakeEmbeddingProvider(), QUERY_LIMITS, tokenizer=tok)
        with pytest.raises(ValidationError):
            await uc.handle(
                EmbedQueriesQuery(texts=("ok", "big"), request_id=None)
            )


class TestWarmupAndDescribe:
    async def test_warmup_returns_status(self) -> None:
        provider = FakeEmbeddingProvider()
        status = await WarmupModel(provider).handle()
        assert status.loaded
        assert provider.warmup_calls == 1

    async def test_warmup_probe_failure_propagates(self) -> None:
        provider = FakeEmbeddingProvider(warmup_error=ProbeFailed("bad dim"))
        with pytest.raises(ProbeFailed):
            await WarmupModel(provider).handle()

    async def test_describe_returns_model_key(self) -> None:
        provider = FakeEmbeddingProvider()
        status = await DescribeModel(provider).handle()
        assert status.model_key == provider.model_id.key
