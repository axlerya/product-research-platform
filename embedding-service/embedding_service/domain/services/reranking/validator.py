"""Доменный сервис ``RerankValidator`` — статическая проверка rerank-запроса."""

from collections.abc import Sequence

from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    EmptyBatchError,
    RequestTooLargeError,
    TextTooLongError,
)
from embedding_service.domain.value_objects.reranking.candidate import (
    RerankCandidate,
)
from embedding_service.domain.value_objects.reranking.limits import (
    RerankLimits,
)
from embedding_service.domain.value_objects.reranking.query import RerankQuery


class RerankValidator:
    """Проверка rerank-запроса против ``RerankLimits`` до инференса.

    Fail-fast: как и синхронный эмбеддинг запросов, первый нарушенный лимит
    отклоняет весь вызов (в presentation → ``INVALID_ARGUMENT``). Пустота
    текстов проверяется на уровне VO (``RerankQuery``/``RerankCandidate``).
    """

    @staticmethod
    def validate(
        query: RerankQuery,
        candidates: Sequence[RerankCandidate],
        limits: RerankLimits,
    ) -> None:
        """Проверяет структурные лимиты rerank-запроса.

        Args:
            query: Текст запроса.
            candidates: Документы-кандидаты.
            limits: Политика лимитов.

        Raises:
            EmptyBatchError: Если нет ни одного документа.
            BatchTooLargeError: Если документов больше ``max_documents``.
            TextTooLongError: Если запрос/документ длиннее лимита символов.
            RequestTooLargeError: Если суммарный размер превышает
                ``max_total_bytes``.
        """
        if not candidates:
            raise EmptyBatchError("Запрос не содержит документов")
        if len(candidates) > limits.max_documents:
            raise BatchTooLargeError(
                f"Слишком много документов: "
                f"{len(candidates)} > {limits.max_documents}"
            )
        if query.char_length > limits.max_query_chars:
            raise TextTooLongError(
                f"Запрос длиннее {limits.max_query_chars} символов: "
                f"{query.char_length}"
            )
        for candidate in candidates:
            if candidate.char_length > limits.max_document_chars:
                raise TextTooLongError(
                    f"Документ длиннее {limits.max_document_chars} символов: "
                    f"{candidate.char_length}"
                )
        total_bytes = len(query.value.encode("utf-8")) + sum(
            len(candidate.text.encode("utf-8")) for candidate in candidates
        )
        if total_bytes > limits.max_total_bytes:
            raise RequestTooLargeError(
                f"Размер запроса {total_bytes} байт превышает "
                f"{limits.max_total_bytes}"
            )
