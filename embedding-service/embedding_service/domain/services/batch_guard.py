"""Доменный сервис ``BatchGuard`` — статическая проверка батча."""

from collections.abc import Sequence

from embedding_service.domain.exceptions import (
    BatchTooLargeError,
    EmptyBatchError,
    RequestTooLargeError,
    TextTooLongError,
)
from embedding_service.domain.value_objects.limits import EmbeddingLimits
from embedding_service.domain.value_objects.request_item import (
    EmbeddingRequestItem,
)


class BatchGuard:
    """Проверка батча против ``EmbeddingLimits`` до всякого инференса.

    Токен-лимит здесь не проверяется — он требует токенайзера (внешний
    порт), поэтому ``TokensExceededError`` поднимается в application.
    """

    @staticmethod
    def validate(
        items: Sequence[EmbeddingRequestItem], limits: EmbeddingLimits
    ) -> None:
        """Проверяет структурные лимиты батча.

        Args:
            items: Элементы входного батча.
            limits: Политика лимитов (свой экземпляр для DOCUMENT/QUERY).

        Raises:
            EmptyBatchError: Если батч пуст.
            BatchTooLargeError: Если текстов больше ``max_texts``.
            TextTooLongError: Если какой-то текст длиннее ``max_text_chars``.
            RequestTooLargeError: Если суммарный размер превышает
                ``max_total_bytes``.
        """
        if not items:
            raise EmptyBatchError("Батч не содержит элементов")
        if len(items) > limits.max_texts:
            raise BatchTooLargeError(
                f"Слишком много текстов: {len(items)} > {limits.max_texts}"
            )
        for item in items:
            if item.text.char_length > limits.max_text_chars:
                raise TextTooLongError(
                    f"Текст длиннее {limits.max_text_chars} символов: "
                    f"{item.text.char_length}"
                )
        total_bytes = sum(
            len(item.text.value.encode("utf-8")) for item in items
        )
        if total_bytes > limits.max_total_bytes:
            raise RequestTooLargeError(
                f"Размер запроса {total_bytes} байт превышает "
                f"{limits.max_total_bytes}"
            )
