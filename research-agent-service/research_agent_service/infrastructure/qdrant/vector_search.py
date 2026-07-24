"""QdrantVectorSearch — read-only гибридный поиск (порт VectorSearchPort).

Читает через алиас коллекции; named-векторы строго "dense"/"sparse";
sparse — без IDF; обязателен фильтр tombstone (is_deleted != true);
слияние dense+sparse — серверный RRF. Никаких записей.
"""

from collections.abc import Mapping
from decimal import Decimal

from qdrant_client import AsyncQdrantClient, models

from research_agent_service.application.dto.retrieval import RetrievedPoint
from research_agent_service.domain.value_objects.query import QueryFilters

_DENSE = "dense"
_SPARSE = "sparse"
_DEFAULT_COLLECTION = "products"


def _opt_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _range(low: Decimal | None, high: Decimal | None) -> models.Range | None:
    if low is None and high is None:
        return None
    return models.Range(
        gte=None if low is None else float(low),
        lte=None if high is None else float(high),
    )


class QdrantVectorSearch:
    """Гибридный dense+sparse поиск с серверным RRF (только чтение)."""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection: str = _DEFAULT_COLLECTION,
    ) -> None:
        self._client = client
        self._collection = collection

    async def hybrid_search(
        self,
        *,
        dense: tuple[float, ...],
        sparse_indices: tuple[int, ...],
        sparse_values: tuple[float, ...],
        filters: QueryFilters | None,
        limit: int,
    ) -> tuple[RetrievedPoint, ...]:
        """Возвращает до limit точек, слитых по RRF (без записи)."""
        response = await self._client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(query=list(dense), using=_DENSE, limit=limit),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=list(sparse_indices),
                        values=list(sparse_values),
                    ),
                    using=_SPARSE,
                    limit=limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=self._filter(filters),
            with_payload=True,
            with_vectors=False,
            limit=limit,
        )
        return tuple(self._point(point) for point in response.points)

    @staticmethod
    def _filter(filters: QueryFilters | None) -> models.Filter:
        must_not = [
            models.FieldCondition(
                key="is_deleted", match=models.MatchValue(value=True)
            )
        ]
        must: list[models.FieldCondition] = []
        if filters is not None:
            keywords = (
                ("category", filters.category),
                ("brand", filters.brand),
                ("supplier", filters.supplier),
            )
            for key, value in keywords:
                if value is not None:
                    must.append(
                        models.FieldCondition(
                            key=key, match=models.MatchValue(value=value)
                        )
                    )
            if filters.in_stock is not None:
                must.append(
                    models.FieldCondition(
                        key="in_stock",
                        match=models.MatchValue(value=filters.in_stock),
                    )
                )
            ranges = (
                ("price", filters.price_min, filters.price_max),
                ("margin_percent", filters.margin_min, filters.margin_max),
            )
            for key, low, high in ranges:
                built = _range(low, high)
                if built is not None:
                    must.append(models.FieldCondition(key=key, range=built))
            if filters.min_rating is not None:
                must.append(
                    models.FieldCondition(
                        key="rating",
                        range=models.Range(gte=float(filters.min_rating)),
                    )
                )
        return models.Filter(must=must or None, must_not=must_not)

    @staticmethod
    def _point(point: models.ScoredPoint) -> RetrievedPoint:
        payload: Mapping[str, object] = point.payload or {}
        return RetrievedPoint(
            product_id=str(payload.get("product_id", point.id)),
            sku=str(payload.get("sku", "")),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            category=str(payload.get("category", "")),
            currency=str(payload.get("currency", "RUB")),
            score=float(point.score),
            price=_opt_decimal(payload.get("price")),
            stock=payload.get("stock"),  # type: ignore[arg-type]
            in_stock=payload.get("in_stock"),  # type: ignore[arg-type]
            margin_percent=_opt_decimal(payload.get("margin_percent")),
        )
