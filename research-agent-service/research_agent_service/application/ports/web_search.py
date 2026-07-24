"""Порт WebSearchProvider — внешний веб-поиск (Tavily/Serper)."""

from typing import Protocol

from research_agent_service.application.dto.web import WebResult


class WebSearchProvider(Protocol):
    """Поставщик внешнего web-поиска."""

    async def search(self, query: str, *, k: int) -> tuple[WebResult, ...]:
        """Возвращает до ``k`` результатов по запросу."""
        ...
