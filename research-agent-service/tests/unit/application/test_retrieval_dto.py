"""Тесты DTO retrieval-пайплайна (конструирование и умолчания)."""

from decimal import Decimal

from research_agent_service.application.dto.catalog import (
    CatalogFetch,
    CatalogProduct,
)
from research_agent_service.application.dto.retrieval import (
    QueryEmbedding,
    RagContext,
    RankedProduct,
    RetrievedPoint,
)
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.money import Money

_RUB = Currency("RUB")


def test_query_embedding_holds_vectors() -> None:
    """QueryEmbedding хранит dense/sparse и водяной знак модели."""
    emb = QueryEmbedding(
        dense=(0.1, 0.2),
        sparse_indices=(3,),
        sparse_values=(0.5,),
        model_version="BAAI/bge-m3",
        token_count=7,
    )

    assert len(emb.dense) == 2
    assert emb.model_version == "BAAI/bge-m3"


def test_retrieved_point_optional_fields_default_none() -> None:
    """Ценовые поля точки Qdrant по умолчанию None (fallback опционален)."""
    point = RetrievedPoint(
        product_id="p1",
        sku="SKU-1",
        name="Наушники",
        description="описание",
        category="Аудио",
        currency="RUB",
        score=0.9,
    )

    assert point.price is None
    assert point.in_stock is None


def test_ranked_product_defaults() -> None:
    """RankedProduct: цена по умолчанию None, price_authoritative=False."""
    product = RankedProduct(
        sku="SKU-1",
        name="Наушники",
        category="Аудио",
        snippet="описание",
    )

    assert product.price is None
    assert product.price_authoritative is False


def test_rag_context_degradations_default_empty() -> None:
    """RagContext без деградаций — пустой кортеж."""
    ctx = RagContext(products=(), citations=())

    assert ctx.degradations == ()


def test_catalog_product_carries_money() -> None:
    """CatalogProduct несёт авторитетную цену как Money."""
    product = CatalogProduct(
        sku="SKU-1",
        name="Наушники",
        category="Аудио",
        brand="B",
        supplier="S",
        price=Money.of("129.99", _RUB),
        cost=Money.of("80.00", _RUB),
        stock=5,
        is_in_stock=True,
        margin_percent=Decimal("38.46"),
    )

    assert product.price.amount == Decimal("129.99")


def test_catalog_fetch_missing_skus_default_empty() -> None:
    """CatalogFetch без отсутствующих sku — пустой кортеж."""
    fetch = CatalogFetch(products=())

    assert fetch.missing_skus == ()
