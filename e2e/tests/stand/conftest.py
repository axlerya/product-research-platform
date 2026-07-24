"""Фикстуры поднятого стенда."""

import os
from collections.abc import Iterator

import httpx
import pytest

from tests.support.stand import Catalog, Qdrant, Stand, wait_until

_READY_TIMEOUT_S = float(os.getenv("STAND_READY_TIMEOUT_S", "600"))


@pytest.fixture(scope="session")
def stand() -> Stand:
    """Адреса компонентов стенда."""
    return Stand.from_env()


@pytest.fixture(scope="session", autouse=True)
def _stand_is_up(stand: Stand) -> None:
    """Падает с понятным сообщением, если стенд не поднят или не прогрет."""
    probes = (
        (f"{stand.catalog}/health", "catalog-api"),
        (f"{stand.agent}/health", "agent-api"),
        (f"{stand.agent_degraded}/health", "agent-api-degraded"),
        (f"{stand.doubles}/health", "test-doubles"),
        (f"{stand.qdrant}/readyz", "qdrant"),
        (f"{stand.embedding_ops}/ready", "embedding"),
        (f"{stand.embedding_ops}/reranker/ready", "reranker"),
    )
    with httpx.Client(timeout=10.0) as client:

        def _probe(url: str) -> bool:
            try:
                return client.get(url).status_code == 200
            except httpx.HTTPError:
                return False

        for url, name in probes:
            wait_until(
                lambda url=url: _probe(url),
                timeout_s=_READY_TIMEOUT_S,
                interval_s=2.0,
                what=f"готовность {name} ({url})",
            )


@pytest.fixture
def http() -> Iterator[httpx.Client]:
    """HTTP-клиент с запасом по таймауту (прогон агента бывает долгим)."""
    with httpx.Client(timeout=120.0) as client:
        yield client


@pytest.fixture
def catalog(http: httpx.Client, stand: Stand) -> Catalog:
    """Клиент каталога для подготовки данных сценария."""
    return Catalog(http, stand.catalog)


@pytest.fixture
def qdrant(http: httpx.Client, stand: Stand) -> Qdrant:
    """Клиент чтения Qdrant."""
    return Qdrant(http, stand.qdrant, stand.collection)
