"""TavilyWebSearch — провайдер web-поиска Tavily (порт WebSearchProvider)."""

import httpx

from research_agent_service.application.dto.web import WebResult

_ENDPOINT = "https://api.tavily.com/search"


class TavilyWebSearch:
    """Web-поиск через Tavily. На ошибке возвращает пусто (деградация)."""

    def __init__(self, *, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def search(self, query: str, *, k: int) -> tuple[WebResult, ...]:
        """Возвращает до k результатов (или пусто при ошибке)."""
        try:
            response = await self._client.post(
                _ENDPOINT,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": k,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return ()
        results = response.json().get("results", ())
        return tuple(
            WebResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content", "")),
                published_at=item.get("published_date"),
            )
            for item in results
        )
