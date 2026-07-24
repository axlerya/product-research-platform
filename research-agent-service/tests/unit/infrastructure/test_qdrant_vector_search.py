"""Тесты QdrantVectorSearch на фейковом клиенте."""

from decimal import Decimal

from qdrant_client import models

from research_agent_service.domain.value_objects.query import QueryFilters
from research_agent_service.infrastructure.qdrant.vector_search import (
    QdrantVectorSearch,
)


class _FakePoint:
    def __init__(self, *, id: object, score: float, payload: object) -> None:
        self.id = id
        self.score = score
        self.payload = payload


class _FakeResponse:
    def __init__(self, points: list[_FakePoint]) -> None:
        self.points = points


class _FakeQdrant:
    def __init__(self, points: list[_FakePoint]) -> None:
        self._points = points
        self.kwargs: dict[str, object] = {}

    async def query_points(self, **kwargs: object) -> _FakeResponse:
        self.kwargs = kwargs
        return _FakeResponse(self._points)


_PAYLOAD = {
    "product_id": "p1",
    "sku": "SKU-1",
    "name": "Наушники",
    "description": "описание",
    "category": "Аудио",
    "currency": "RUB",
    "price": 129.99,
    "stock": 5,
    "in_stock": True,
    "margin_percent": 38.46,
}


def _adapter(
    points: list[_FakePoint],
) -> tuple[QdrantVectorSearch, _FakeQdrant]:
    fake = _FakeQdrant(points)
    return QdrantVectorSearch(client=fake), fake


async def _search(
    adapter: QdrantVectorSearch, filters: QueryFilters | None
) -> tuple:
    return await adapter.hybrid_search(
        dense=(0.1,),
        sparse_indices=(1,),
        sparse_values=(0.5,),
        filters=filters,
        limit=10,
    )


async def test_query_uses_named_vectors_and_tombstone_filter() -> None:
    """Запрос: named-векторы dense/sparse, RRF, must_not is_deleted."""
    adapter, fake = _adapter([])

    await _search(adapter, None)

    assert fake.kwargs["collection_name"] == "products"
    usings = {p.using for p in fake.kwargs["prefetch"]}
    assert usings == {"dense", "sparse"}
    assert isinstance(fake.kwargs["query"], models.FusionQuery)
    assert fake.kwargs["query_filter"].must_not[0].key == "is_deleted"


async def test_parses_point() -> None:
    """Точка Qdrant разбирается в RetrievedPoint (цена float→Decimal)."""
    adapter, _ = _adapter([_FakePoint(id="p1", score=0.9, payload=_PAYLOAD)])

    result = await _search(adapter, None)

    assert result[0].sku == "SKU-1"
    assert result[0].price == Decimal("129.99")
    assert result[0].score == 0.9


async def test_empty_payload_falls_back_to_id() -> None:
    """Пустой payload → product_id из id точки, цена None."""
    adapter, _ = _adapter([_FakePoint(id="p9", score=0.5, payload=None)])

    result = await _search(adapter, None)

    assert result[0].product_id == "p9"
    assert result[0].price is None


async def test_full_filter_builds_all_conditions() -> None:
    """Полный набор фасетов → все условия в must."""
    adapter, fake = _adapter([])
    filters = QueryFilters(
        category="Аудио",
        brand="B",
        supplier="S",
        in_stock=True,
        price_min=Decimal("10"),
        price_max=Decimal("100"),
        min_rating=Decimal("4"),
        margin_min=Decimal("5"),
        margin_max=Decimal("40"),
    )

    await _search(adapter, filters)

    keys = {c.key for c in fake.kwargs["query_filter"].must}
    assert {
        "category",
        "brand",
        "supplier",
        "in_stock",
        "price",
        "margin_percent",
        "rating",
    } <= keys


async def test_mixed_range_filter() -> None:
    """Односторонний диапазон: gte задан, lte None."""
    adapter, fake = _adapter([])

    await _search(
        adapter, QueryFilters(price_min=Decimal("10"), margin_max=Decimal("40"))
    )

    must = fake.kwargs["query_filter"].must
    price = next(c for c in must if c.key == "price")
    assert price.range.gte == 10.0
    assert price.range.lte is None


async def test_empty_filter_only_tombstone() -> None:
    """Пустые фильтры → must=None, остаётся только tombstone must_not."""
    adapter, fake = _adapter([])

    await _search(adapter, QueryFilters())

    assert fake.kwargs["query_filter"].must is None
