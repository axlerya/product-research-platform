"""Use case U2 ``EmbedQuery`` — синхронный unary запрос (fail-fast)."""

from embedding_service.application.dto import EmbedQueryQuery
from embedding_service.application.exceptions import to_application_error
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.application.ports.tokenizer import Tokenizer
from embedding_service.domain.exceptions import (
    DomainError,
    TokensExceededError,
)
from embedding_service.domain.services.batch_guard import BatchGuard
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.item_result import (
    EmbeddingItemResult,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount

_QUERY_ID = TextId("query")


class EmbedQuery:
    """Эмбеддит один поисковый запрос; любой невалидный вход — fail-fast."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        limits: EmbeddingLimits,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self._provider = provider
        self._limits = limits
        self._tokenizer = tokenizer

    async def handle(self, query: EmbedQueryQuery) -> EmbeddingItemResult:
        try:
            text = EmbeddingText(query.text)
            BatchGuard.validate(
                [EmbeddingRequestItem(_QUERY_ID, text)], self._limits
            )
            token_count = TokenCount(0)
            if self._tokenizer is not None:
                token_count = self._tokenizer.count_tokens(text)
                if token_count.value > self._limits.max_tokens:
                    raise TokensExceededError(
                        f"Токенов больше {self._limits.max_tokens}"
                    )
        except DomainError as exc:
            raise to_application_error(exc) from exc
        [embedding] = await self._provider.embed(
            [text], kind=EmbeddingKind.QUERY
        )
        return EmbeddingItemResult.ok(_QUERY_ID, embedding, token_count)
