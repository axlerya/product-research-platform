"""Use case U1 ``EmbedDocuments`` — асинхронный документный батч (партиал)."""

from collections.abc import Sequence
from dataclasses import dataclass

from embedding_service.application.dto import (
    DocumentsGenerated,
    EmbedDocumentsCommand,
    RawTextItem,
)
from embedding_service.application.exceptions import (
    to_application_error,
    to_item_error,
)
from embedding_service.application.ports.embedding_provider import (
    EmbeddingProvider,
)
from embedding_service.application.ports.tokenizer import Tokenizer
from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    DomainError,
    EmptyBatchError,
    RequestTooLargeError,
    TextTooLongError,
    TokensExceededError,
)
from embedding_service.domain.services.assembler import (
    EmbeddingAssembler,
    Outcome,
)
from embedding_service.domain.value_objects.embedding_kind import EmbeddingKind
from embedding_service.domain.value_objects.embedding_text import EmbeddingText
from embedding_service.domain.value_objects.item_error import ItemError
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.text_id import TextId
from embedding_service.domain.value_objects.token_count import TokenCount


@dataclass(slots=True)
class _Prepared:
    """Результат пер-элементной подготовки: валидный текст либо отказ."""

    text_id: TextId
    text: EmbeddingText | None
    token_count: TokenCount
    error: ItemError | None


class EmbedDocuments:
    """Валидирует батч, эмбеддит валидные тексты, собирает партиал.

    Структурные ошибки батча (пусто/много/размер/битый id) — poison
    (``ValidationError`` → park). Пер-элементные (пусто/длинно/токены) —
    партиал: битый элемент едет ``status:"error"``, остальные считаются.
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        limits: EmbeddingLimits,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self._provider = provider
        self._limits = limits
        self._tokenizer = tokenizer

    async def handle(
        self, command: EmbedDocumentsCommand
    ) -> DocumentsGenerated:
        raw = command.items
        try:
            text_ids = self._validate_structure(raw)
        except DomainError as exc:
            raise to_application_error(exc) from exc

        prepared = [
            self._prepare(text_id, item.text)
            for text_id, item in zip(text_ids, raw, strict=True)
        ]
        valid_texts = [p.text for p in prepared if p.text is not None]
        embeddings = (
            await self._provider.embed(valid_texts, kind=EmbeddingKind.DOCUMENT)
            if valid_texts
            else []
        )

        outcomes: list[Outcome] = []
        emb_iter = iter(embeddings)
        for prep in prepared:
            if prep.error is not None:
                outcomes.append(prep.error)
            else:
                outcomes.append((next(emb_iter), prep.token_count))

        result = EmbeddingAssembler.assemble(
            [p.text_id for p in prepared], outcomes, self._provider.model_id
        )
        return DocumentsGenerated(
            request_id=command.request_id,
            model_key=self._provider.model_id.key,
            dim=self._provider.model_id.dim,
            results=result.items,
        )

    def _validate_structure(self, raw: Sequence[RawTextItem]) -> list[TextId]:
        if not raw:
            raise EmptyBatchError("Батч не содержит элементов")
        if len(raw) > self._limits.max_texts:
            raise BatchTooLargeError(f"Слишком много текстов: {len(raw)}")
        total = sum(len(item.text.encode("utf-8")) for item in raw)
        if total > self._limits.max_total_bytes:
            raise RequestTooLargeError(
                f"Размер запроса {total} байт превышает лимит"
            )
        return [TextId(item.text_id) for item in raw]

    def _prepare(self, text_id: TextId, raw_text: str) -> _Prepared:
        try:
            text = EmbeddingText(raw_text)
            if text.char_length > self._limits.max_text_chars:
                raise TextTooLongError(
                    f"Текст длиннее {self._limits.max_text_chars} символов"
                )
            token_count = TokenCount(0)
            if self._tokenizer is not None:
                token_count = self._tokenizer.count_tokens(text)
                if token_count.value > self._limits.max_tokens:
                    raise TokensExceededError(
                        f"Токенов больше {self._limits.max_tokens}"
                    )
            return _Prepared(text_id, text, token_count, None)
        except DomainError as exc:
            return _Prepared(text_id, None, TokenCount(0), to_item_error(exc))
