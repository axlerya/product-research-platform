"""Тесты ProductCatalogRagService — retrieval-пайплайн и деградации."""

from datetime import UTC, datetime
from decimal import Decimal

from research_agent_service.application.dto.catalog import (
    CatalogFetch,
    CatalogProduct,
)
from research_agent_service.application.dto.retrieval import (
    QueryEmbedding,
    RankedDoc,
    RerankDocument,
    RetrievedPoint,
)
from research_agent_service.application.exceptions import (
    CatalogUnavailable,
    RerankerUnavailable,
)
from research_agent_service.application.services.product_catalog_rag import (
    ProductCatalogRagService,
)
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.enums import CitationType
from research_agent_service.domain.value_objects.money import Money

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_RUB = Currency("RUB")


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeEmbedding:
    async def embed_query(self, text: str) -> QueryEmbedding:
        return QueryEmbedding(
            dense=(0.1,),
            sparse_indices=(1,),
            sparse_values=(0.5,),
            model_version="bge-m3",
            token_count=3,
        )


class _FakeVectorSearch:
    def __init__(self, points: tuple[RetrievedPoint, ...]) -> None:
        self._points = points

    async def hybrid_search(
        self, **_kwargs: object
    ) -> tuple[RetrievedPoint, ...]:
        return self._points


class _FakeReranker:
    def __init__(self, ranked: tuple[RankedDoc, ...] | None) -> None:
        self._ranked = ranked

    async def rerank(
        self,
        query: str,
        documents: tuple[RerankDocument, ...],
        *,
        top_n: int,
    ) -> tuple[RankedDoc, ...]:
        if self._ranked is None:
            raise RerankerUnavailable
        return self._ranked


class _FakeCatalog:
    def __init__(self, fetch: CatalogFetch | None) -> None:
        self._fetch = fetch

    async def get_products_by_skus(self, skus: tuple[str, ...]) -> CatalogFetch:
        if self._fetch is None:
            raise CatalogUnavailable
        return self._fetch


def _point(sku: str, product_id: str, score: float = 0.9) -> RetrievedPoint:
    return RetrievedPoint(
        product_id=product_id,
        sku=sku,
        name=f"Товар {sku}",
        description="описание",
        category="Аудио",
        currency="RUB",
        score=score,
        price=Decimal("100.00"),
        stock=5,
        in_stock=True,
        margin_percent=Decimal("20.00"),
    )


def _catalog_product(sku: str, price: str) -> CatalogProduct:
    return CatalogProduct(
        sku=sku,
        name=f"Товар {sku}",
        category="Аудио",
        brand="B",
        supplier="S",
        price=Money.of(price, _RUB),
        cost=Money.of("50.00", _RUB),
        stock=9,
        is_in_stock=True,
        margin_percent=Decimal("38.00"),
    )


def _service(
    *,
    points: tuple[RetrievedPoint, ...],
    ranked: tuple[RankedDoc, ...] | None,
    fetch: CatalogFetch | None,
) -> ProductCatalogRagService:
    return ProductCatalogRagService(
        embedding=_FakeEmbedding(),
        vector_search=_FakeVectorSearch(points),
        reranker=_FakeReranker(ranked),
        catalog=_FakeCatalog(fetch),
        clock=_FakeClock(),
    )


async def test_happy_path_authoritative_and_reranked() -> None:
    """Полный путь: rerank переупорядочивает, цены — авторитетные из catalog."""
    points = (_point("SKU-1", "p1"), _point("SKU-2", "p2"))
    ranked = (
        RankedDoc(id="SKU-2", index=1, score=Decimal("0.95")),
        RankedDoc(id="SKU-1", index=0, score=Decimal("0.80")),
    )
    fetch = CatalogFetch(
        products=(
            _catalog_product("SKU-1", "129.99"),
            _catalog_product("SKU-2", "199.99"),
        )
    )
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert [p.sku for p in ctx.products] == ["SKU-2", "SKU-1"]
    assert ctx.products[0].price == Money.of("199.99", _RUB)
    assert ctx.products[0].price_authoritative is True
    assert ctx.products[0].rerank_score == Decimal("0.95")
    assert ctx.degradations == ()


async def test_dedupes_by_product_id() -> None:
    """Дубли одной точки (по product_id) схлопываются."""
    points = (
        _point("SKU-1", "p1"),
        _point("SKU-1-chunk", "p1"),  # тот же product_id
        _point("SKU-2", "p2"),
    )
    ranked = (
        RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),
        RankedDoc(id="SKU-2", index=1, score=Decimal("0.8")),
    )
    fetch = CatalogFetch(
        products=(
            _catalog_product("SKU-1", "100.00"),
            _catalog_product("SKU-2", "200.00"),
        )
    )
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert {p.sku for p in ctx.products} == {"SKU-1", "SKU-2"}


async def test_reranker_unavailable_degrades_to_rrf_order() -> None:
    """Reranker недоступен → порядок RRF, без скора, деградация."""
    points = (_point("SKU-1", "p1"), _point("SKU-2", "p2"))
    fetch = CatalogFetch(
        products=(
            _catalog_product("SKU-1", "100.00"),
            _catalog_product("SKU-2", "200.00"),
        )
    )
    service = _service(points=points, ranked=None, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert [p.sku for p in ctx.products] == ["SKU-1", "SKU-2"]
    assert ctx.products[0].rerank_score is None
    assert any(d.dependency == "reranker" for d in ctx.degradations)


async def test_catalog_unavailable_falls_back_to_readmodel() -> None:
    """Catalog недоступен → цены из Qdrant с пометкой неавторитетности."""
    points = (_point("SKU-1", "p1"),)
    ranked = (RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),)
    service = _service(points=points, ranked=ranked, fetch=None)

    ctx = await service.retrieve("наушники")

    assert ctx.products[0].price == Money.of("100.00", _RUB)
    assert ctx.products[0].price_authoritative is False
    assert any(d.dependency == "catalog" for d in ctx.degradations)


async def test_missing_skus_are_excluded() -> None:
    """Товары из missing_skus (исчезли из catalog) исключаются."""
    points = (_point("SKU-1", "p1"), _point("SKU-2", "p2"))
    ranked = (
        RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),
        RankedDoc(id="SKU-2", index=1, score=Decimal("0.8")),
    )
    fetch = CatalogFetch(
        products=(_catalog_product("SKU-2", "200.00"),),
        missing_skus=("SKU-1",),  # первый в порядке — цикл продолжается дальше
    )
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert [p.sku for p in ctx.products] == ["SKU-2"]


async def test_builds_product_citations() -> None:
    """Каждый товар порождает product-цитату с ref=sku и позицией."""
    points = (_point("SKU-1", "p1"),)
    ranked = (RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),)
    fetch = CatalogFetch(products=(_catalog_product("SKU-1", "100.00"),))
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert len(ctx.citations) == 1
    citation = ctx.citations[0]
    assert citation.source_type is CitationType.PRODUCT
    assert citation.ref == "SKU-1"
    assert citation.position == 0
    assert citation.retrieved_at == _NOW


async def test_empty_search_returns_empty_context() -> None:
    """Пустая выдача Qdrant → пустой контекст без обращений дальше."""
    service = _service(points=(), ranked=(), fetch=CatalogFetch(products=()))

    ctx = await service.retrieve("наушники")

    assert ctx.products == ()
    assert ctx.citations == ()


async def test_not_returned_and_not_missing_is_excluded() -> None:
    """Sku, не вернувшийся из catalog и не помеченный missing, исключается."""
    points = (_point("SKU-1", "p1"), _point("SKU-2", "p2"))
    ranked = (
        RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),
        RankedDoc(id="SKU-2", index=1, score=Decimal("0.8")),
    )
    # SKU-1 не вернулся и не в missing → пропущен, цикл идёт дальше к SKU-2
    fetch = CatalogFetch(products=(_catalog_product("SKU-2", "200.00"),))
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert [p.sku for p in ctx.products] == ["SKU-2"]


async def test_readmodel_fallback_without_price_yields_none() -> None:
    """Catalog недоступен и в read-model нет цены → price=None."""
    point = RetrievedPoint(
        product_id="p1",
        sku="SKU-1",
        name="Товар",
        description="о",
        category="Аудио",
        currency="RUB",
        score=0.9,
        price=None,
    )
    ranked = (RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),)
    service = _service(points=(point,), ranked=ranked, fetch=None)

    ctx = await service.retrieve("наушники")

    assert ctx.products[0].price is None
    assert ctx.products[0].price_authoritative is False


async def test_rerank_ids_not_among_candidates_are_ignored() -> None:
    """RankedDoc с неизвестным id (нет среди кандидатов) игнорируется."""
    points = (_point("SKU-1", "p1"),)
    ranked = (
        RankedDoc(id="SKU-1", index=0, score=Decimal("0.9")),
        RankedDoc(id="SKU-GHOST", index=1, score=Decimal("0.8")),
    )
    fetch = CatalogFetch(products=(_catalog_product("SKU-1", "100.00"),))
    service = _service(points=points, ranked=ranked, fetch=fetch)

    ctx = await service.retrieve("наушники")

    assert [p.sku for p in ctx.products] == ["SKU-1"]
