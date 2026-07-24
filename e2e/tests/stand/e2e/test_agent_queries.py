"""Сквозные сценарии запроса: инструменты, идемпотентность, деградация.

LLM и внешний web-поиск заменены детерминированными провайдерами; всё
остальное на пути запроса — боевое: gRPC-эмбеддинг запроса, гибридный поиск в
Qdrant, реранкинг cross-encoder, REST каталога, Redis и Postgres.
"""

import pytest

from tests.support.stand import (
    Catalog,
    Qdrant,
    Stand,
    ask,
    citation_refs,
    degradation_pairs,
    indexed_point,
    unique_suffix,
)

pytestmark = pytest.mark.e2e

# Цены и себестоимости среза: маржа 60% / 25% / 80%, медиана цены — 200.
_SLICE = (("100.00", "40.00"), ("200.00", "150.00"), ("300.00", "60.00"))


@pytest.fixture
def indexed_slice(catalog: Catalog, qdrant: Qdrant) -> dict:
    """Три проиндексированных товара в собственной категории."""
    suffix = unique_suffix()
    category = f"E2ECAT-{suffix}"
    products = []
    for index, (price, cost) in enumerate(_SLICE, start=1):
        created = catalog.create(
            sku=f"E2E-{suffix}-{index}",
            name=f"Гарнитура {suffix} модель {index}",
            description=(
                f"Беспроводная гарнитура серии {suffix}, ревизия {index}."
            ),
            category=category,
            price=price,
            cost=cost,
        )
        products.append(created)
    for created in products:
        indexed_point(qdrant, created["id"])
    return {"category": category, "suffix": suffix, "products": products}


def test_rag_only_query_uses_single_tool(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Запрос без ценовых и рыночных маркеров идёт только в RAG."""
    suffix = indexed_slice["suffix"]

    answer = ask(http, stand.agent, f"найди гарнитуру {suffix}")

    assert answer["used_tools"] == ["product_catalog_rag"]
    assert {c["source_type"] for c in answer["citations"]} == {"product"}
    refs = set(citation_refs(answer, "product"))
    assert refs & {product["sku"] for product in indexed_slice["products"]}
    assert answer["degradations"] == []


def test_margin_analysis_query_uses_price_tool(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Запрос о маржинальности считается инструментом ценового анализа."""
    category = indexed_slice["category"]

    answer = ask(
        http, stand.agent, f"посчитай маржинальность, категория {category}"
    )

    assert answer["used_tools"] == ["price_analysis"]
    refs = citation_refs(answer, "price_analysis")
    assert len(refs) == 1
    assert refs[0].startswith("pa-")
    # Числа в ответе взяты из каталога, а не досочинены моделью.
    assert "3 товаров" in answer["answer"]
    assert "200.00 RUB" in answer["answer"]


def test_web_search_query_returns_external_citations(
    stand: Stand, http
) -> None:
    """Рыночный вопрос уходит во внешний поиск и цитирует его ссылки."""
    answer = ask(http, stand.agent, "что нового на рынке беспроводных гарнитур")

    assert answer["used_tools"] == ["web_search"]
    refs = citation_refs(answer, "web")
    assert len(refs) == 3
    assert all(ref.startswith("https://example.test/") for ref in refs)


def test_multi_tool_query_combines_sources(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Составной запрос вызывает три инструмента за один прогон."""
    category = indexed_slice["category"]

    answer = ask(
        http,
        stand.agent,
        f"покажи товары, маржинальность и рынок, категория {category}",
    )

    assert set(answer["used_tools"]) == {
        "product_catalog_rag",
        "price_analysis",
        "web_search",
    }
    assert {c["source_type"] for c in answer["citations"]} == {
        "product",
        "price_analysis",
        "web",
    }
    assert citation_refs(answer, "price_analysis")[0].startswith("pa-")


def test_idempotent_repeat_returns_same_run(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Повтор с тем же ключом реплеит прежний прогон, а не создаёт новый."""
    suffix = indexed_slice["suffix"]
    question = f"найди гарнитуру {suffix}"
    key = f"idem-{suffix}"

    first = ask(http, stand.agent, question, idempotency_key=key)
    second = ask(http, stand.agent, question, idempotency_key=key)
    other = ask(http, stand.agent, question, idempotency_key=f"{key}-other")

    assert second["agent_run_id"] == first["agent_run_id"]
    assert second["answer"] == first["answer"]
    assert second["citations"] == first["citations"]
    assert other["agent_run_id"] != first["agent_run_id"]


def test_degrades_when_reranker_unavailable(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Недоступный reranker понижает уверенность, но ответ остаётся."""
    suffix = indexed_slice["suffix"]

    answer = ask(http, stand.agent_degraded, f"найди гарнитуру {suffix}")

    assert ("reranker", "unavailable") in degradation_pairs(answer)
    assert citation_refs(answer, "product")
    assert answer["confidence"] == "medium"
    assert "reranker" in answer["answer"]


def test_healthy_instance_has_no_reranker_degradation(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Контрольная проверка: на исправном инстансе реранкинг отработал."""
    suffix = indexed_slice["suffix"]

    answer = ask(http, stand.agent, f"найди гарнитуру {suffix}")

    assert not degradation_pairs(answer)
    assert all(
        citation["score"] is not None
        for citation in answer["citations"]
        if citation["source_type"] == "product"
    )
