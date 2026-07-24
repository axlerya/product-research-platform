"""Тесты web-провайдеров Tavily/Serper на httpx.MockTransport."""

from collections.abc import Callable

import httpx

from research_agent_service.infrastructure.websearch.serper import (
    SerperWebSearch,
)
from research_agent_service.infrastructure.websearch.tavily import (
    TavilyWebSearch,
)


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_tavily_parses_results() -> None:
    """Tavily: content → snippet, published_date → published_at."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Наушники обзор",
                        "url": "https://a.example",
                        "content": "текст",
                        "published_date": "2026-01-01",
                    }
                ]
            },
        )

    provider = TavilyWebSearch(client=_transport(handler), api_key="k")
    results = await provider.search("наушники", k=5)

    assert results[0].url == "https://a.example"
    assert results[0].snippet == "текст"
    assert results[0].published_at == "2026-01-01"


async def test_tavily_returns_empty_on_error() -> None:
    """Tavily: HTTP-ошибка → пусто (деградация)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    provider = TavilyWebSearch(client=_transport(handler), api_key="k")

    assert await provider.search("q", k=3) == ()


async def test_serper_parses_organic_results() -> None:
    """Serper: link → url, snippet → snippet."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-KEY"] == "k"
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "title": "Товар",
                        "link": "https://b.example",
                        "snippet": "описание",
                    }
                ]
            },
        )

    provider = SerperWebSearch(client=_transport(handler), api_key="k")
    results = await provider.search("товар", k=5)

    assert results[0].url == "https://b.example"
    assert results[0].snippet == "описание"
    assert results[0].published_at is None


async def test_serper_returns_empty_on_error() -> None:
    """Serper: HTTP-ошибка → пусто (деградация)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    provider = SerperWebSearch(client=_transport(handler), api_key="k")

    assert await provider.search("q", k=3) == ()


async def test_tavily_calls_public_endpoint_by_default() -> None:
    """Без base_url провайдер ходит в публичный API Tavily."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"results": []})

    provider = TavilyWebSearch(client=_transport(handler), api_key="k")
    await provider.search("q", k=1)

    assert seen == ["https://api.tavily.com/search"]


async def test_tavily_honours_configured_base_url() -> None:
    """Заданный base_url перенаправляет запрос на свой эндпоинт."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"results": []})

    provider = TavilyWebSearch(
        client=_transport(handler),
        api_key="k",
        base_url="http://doubles:8000/",
    )
    await provider.search("q", k=1)

    assert seen == ["http://doubles:8000/search"]


async def test_serper_calls_public_endpoint_by_default() -> None:
    """Без base_url провайдер ходит в публичный API Serper."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"organic": []})

    provider = SerperWebSearch(client=_transport(handler), api_key="k")
    await provider.search("q", k=1)

    assert seen == ["https://google.serper.dev/search"]


async def test_serper_honours_configured_base_url() -> None:
    """Заданный base_url перенаправляет запрос на свой эндпоинт."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"organic": []})

    provider = SerperWebSearch(
        client=_transport(handler), api_key="k", base_url="http://doubles:8000"
    )
    await provider.search("q", k=1)

    assert seen == ["http://doubles:8000/search"]
