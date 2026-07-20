"""Use case U3 ``EmbedQueries`` — синхронный батч запросов (fail-fast)."""

from embedding_service.application.dto import EmbedQueriesQuery
from embedding_service.application.exceptions import to_application_error
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.application.ports.tokenizer import Tokenizer
from embedding_service.domain.exceptions import (
    DomainError,
    TokensExceededError,
)
from embedding_service.domain.services.assembler import (
    EmbeddingAssembler,
    Outcome,
)
from embedding_service.domain.services.batch_guard import BatchGuard
from embedding_service.domain.value_objects.batch_result import (
    BatchEmbeddingResult,
)
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


class EmbedQueries:
    """Эмбеддит батч запросов; любой невалидный элемент валит весь вызов."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        limits: EmbeddingLimits,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self._provider = provider
        self._limits = limits
        self._tokenizer = tokenizer

    async def handle(self, query: EmbedQueriesQuery) -> BatchEmbeddingResult:
        try:
            texts = [EmbeddingText(t) for t in query.texts]
            items = [
                EmbeddingRequestItem(TextId(str(index)), text)
                for index, text in enumerate(texts)
            ]
            BatchGuard.validate(items, self._limits)
            token_counts = [self._count(text) for text in texts]
        except DomainError as exc:
            raise to_application_error(exc) from exc
        embeddings = await self._provider.embed(texts, kind=EmbeddingKind.QUERY)
        outcomes: list[Outcome] = [
            (embedding, count)
            for embedding, count in zip(embeddings, token_counts, strict=True)
        ]
        return EmbeddingAssembler.assemble(
            [item.text_id for item in items],
            outcomes,
            self._provider.model_id,
        )

    def _count(self, text: EmbeddingText) -> TokenCount:
        if self._tokenizer is None:
            return TokenCount(0)
        count = self._tokenizer.count_tokens(text)
        if count.value > self._limits.max_tokens:
            raise TokensExceededError(
                f"Токенов больше {self._limits.max_tokens}"
            )
        return count
