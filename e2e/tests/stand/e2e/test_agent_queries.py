"""Сквозные сценарии запроса: инструменты, идемпотентность, деградация.

Весь путь запроса боевой: gRPC-эмбеддинг, гибридный поиск в Qdrant,
реранкинг cross-encoder, REST каталога, Redis и Postgres. LLM и web-поиск
могут быть как детерминированными дублями, так и живыми провайдерами —
набор обязан проходить в обоих случаях.

Отсюда правило: проверяем **контракты платформы**, а не поведение модели.
Какие инструменты вызвать, сколько раз и какими словами изложить результат —
решает модель, и на живом провайдере эти решения меняются от прогона к
прогону. Гарантии платформы другие и проверяемые: затребованный инструмент
исполнен, у каждого факта есть цитата нужного типа с валидной ссылкой,
деградации зависимостей отражены в ответе, повтор по ключу идемпотентен.
Точное равенство ``used_tools`` и поиск подстрок в тексте ответа — это
проверка модели, и здесь им не место.
"""

import re

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

# Детерминированный идентификатор среза, на который ссылается цитата
# ценового анализа (см. analysis_ref в catalog-service).
_ANALYSIS_REF = re.compile(r"^pa-[0-9a-f]{16}$")


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


def test_catalog_query_cites_indexed_products(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Поиск по каталогу находит только что проиндексированные товары."""
    suffix = indexed_slice["suffix"]

    answer = ask(http, stand.agent, f"найди гарнитуру {suffix}")

    assert "product_catalog_rag" in answer["used_tools"]
    refs = set(citation_refs(answer, "product"))
    assert refs & {product["sku"] for product in indexed_slice["products"]}
    assert answer["degradations"] == []


def test_margin_analysis_cites_reproducible_slice(
    indexed_slice: dict, stand: Stand, http
) -> None:
    """Запрос о маржинальности считается инструментом ценового анализа.

    Цитата обязана ссылаться на детерминированный идентификатор среза: по
    нему результат воспроизводится в каталоге, то есть число в ответе не
    выдумано моделью. Сами числа тут не сверяем — их корректность закрыта
    контрактным тестом каталога.
    """
    category = indexed_slice["category"]

    answer = ask(
        http, stand.agent, f"посчитай маржинальность, категория {category}"
    )

    assert "price_analysis" in answer["used_tools"]
    refs = citation_refs(answer, "price_analysis")
    assert refs
    assert all(_ANALYSIS_REF.fullmatch(ref) for ref in refs)


def test_web_search_query_returns_external_citations(
    stand: Stand, http
) -> None:
    """Рыночный вопрос уходит во внешний поиск и цитирует его ссылки.

    Ссылка берётся из ответа провайдера как есть — санитайзер чистит только
    заголовок и сниппет. Поэтому проверяем форму ссылки, а не конкретный
    домен: он зависит от того, дубль сейчас за поиском или живой провайдер.
    """
    answer = ask(http, stand.agent, "что нового на рынке беспроводных гарнитур")

    assert "web_search" in answer["used_tools"]
    refs = citation_refs(answer, "web")
    assert refs
    assert all(ref.startswith(("http://", "https://")) for ref in refs)


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

    # Сколько именно инструментов позовёт модель — её решение; платформа
    # обязана исполнить несколько за один прогон и слить их provenance.
    assert len(set(answer["used_tools"])) >= 2
    types = {citation["source_type"] for citation in answer["citations"]}
    assert len(types) >= 2
    assert types <= {"product", "price_analysis", "web"}


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
