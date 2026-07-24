"""Прикладной сервис web-поиска (инструмент web_search)."""

from research_agent_service.application.dto.web import WebResult
from research_agent_service.application.ports.sanitizer import (
    ContentSanitizerPort,
)
from research_agent_service.application.ports.web_search import (
    WebSearchProvider,
)


class WebSearchService:
    """Внешний поиск с санитизацией результатов.

    URL берётся из ответа провайдера (канонический), а заголовок и сниппет
    прогоняются через санитайзер: недоверенный текст не выдаётся как есть.
    """

    def __init__(
        self,
        *,
        provider: WebSearchProvider,
        sanitizer: ContentSanitizerPort,
    ) -> None:
        self._provider = provider
        self._sanitizer = sanitizer

    async def search(self, query: str, *, k: int) -> tuple[WebResult, ...]:
        """Ищет во внешнем провайдере и обеззараживает результаты."""
        raw_results = await self._provider.search(query, k=k)
        return tuple(
            WebResult(
                title=self._sanitizer.sanitize(result.title),
                url=result.url,
                snippet=self._sanitizer.sanitize(result.snippet),
                published_at=result.published_at,
            )
            for result in raw_results
        )
