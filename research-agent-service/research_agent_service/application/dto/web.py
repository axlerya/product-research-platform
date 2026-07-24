"""DTO web-поиска."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebResult:
    """Обеззараженный результат web-поиска.

    Attributes:
        title: Заголовок.
        url: Канонический URL из ответа провайдера (не из тела страницы).
        snippet: Непроверяемый фрагмент (после санитизации).
        published_at: Дата публикации, если известна.
    """

    title: str
    url: str
    snippet: str
    published_at: str | None = None
