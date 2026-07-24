"""SerperWebSearch — провайдер web-поиска Serper (порт WebSearchProvider)."""

import httpx

from research_agent_service.application.dto.web import WebResult

_ENDPOINT = "https://google.serper.dev/search"


class SerperWebSearch:
    """Web-поиск через Serper. На ошибке возвращает пусто (деградация)."""

    def __init__(self, *, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def search(self, query: str, *, k: int) -> tuple[WebResult, ...]:
        """Возвращает до k результатов (или пусто при ошибке)."""
        try:
            response = await self._client.post(
                _ENDPOINT,
                headers={"X-API-KEY": self._api_key},
                json={"q": query, "num": k},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return ()
        organic = response.json().get("organic", ())
        return tuple(
            WebResult(
                title=str(item.get("title", "")),
                url=str(item.get("link", "")),
                snippet=str(item.get("snippet", "")),
                published_at=item.get("date"),
            )
            for item in organic
        )
