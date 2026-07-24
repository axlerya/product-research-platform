"""Прикладной сервис product_catalog_rag — retrieval-пайплайн.

embedding-service → Qdrant (hybrid + RRF) → дедуп по товару → rerank →
авторитетное обогащение из catalog. Всё read-only; при недоступности
reranker или catalog пайплайн деградирует, а не падает.
"""

from datetime import datetime
from decimal import Decimal

from research_agent_service.application.dto.catalog import CatalogProduct
from research_agent_service.application.dto.retrieval import (
    RagContext,
    RankedProduct,
    RerankDocument,
    RetrievedPoint,
)
from research_agent_service.application.exceptions import (
    CatalogUnavailable,
    RerankerUnavailable,
)
from research_agent_service.application.ports.catalog import CatalogPort
from research_agent_service.application.ports.clock import Clock
from research_agent_service.application.ports.embedding import EmbeddingPort
from research_agent_service.application.ports.reranker import RerankerPort
from research_agent_service.application.ports.vector_search import (
    VectorSearchPort,
)
from research_agent_service.domain.policies import (
    DEFAULT_AGENT_LOOP_POLICY,
    AgentLoopPolicy,
)
from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.currency import Currency
from research_agent_service.domain.value_objects.degradation import Degradation
from research_agent_service.domain.value_objects.enums import CitationType
from research_agent_service.domain.value_objects.money import Money
from research_agent_service.domain.value_objects.query import QueryFilters

_OrderedPoint = tuple[RetrievedPoint, Decimal | None]


class ProductCatalogRagService:
    """Инструмент product_catalog_rag: поиск и обогащение товаров."""

    def __init__(
        self,
        *,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        reranker: RerankerPort,
        catalog: CatalogPort,
        clock: Clock,
        policy: AgentLoopPolicy = DEFAULT_AGENT_LOOP_POLICY,
    ) -> None:
        self._embedding = embedding
        self._vector_search = vector_search
        self._reranker = reranker
        self._catalog = catalog
        self._clock = clock
        self._policy = policy

    async def retrieve(
        self, query: str, *, filters: QueryFilters | None = None
    ) -> RagContext:
        """Возвращает отранжированные товары и их источники."""
        degradations: list[Degradation] = []
        embedding = await self._embedding.embed_query(query)
        points = await self._vector_search.hybrid_search(
            dense=embedding.dense,
            sparse_indices=embedding.sparse_indices,
            sparse_values=embedding.sparse_values,
            filters=filters,
            limit=self._policy.rerank_input_max,
        )
        points = self._dedupe_by_product(points)
        ordered = await self._rerank_or_skip(query, points, degradations)
        products = await self._enrich(ordered, degradations)
        citations = self._build_citations(products, now=self._clock.now())
        return RagContext(
            products=products,
            citations=citations,
            degradations=tuple(degradations),
        )

    @staticmethod
    def _dedupe_by_product(
        points: tuple[RetrievedPoint, ...],
    ) -> tuple[RetrievedPoint, ...]:
        seen: set[str] = set()
        unique: list[RetrievedPoint] = []
        for point in points:
            if point.product_id in seen:
                continue
            seen.add(point.product_id)
            unique.append(point)
        return tuple(unique)

    async def _rerank_or_skip(
        self,
        query: str,
        points: tuple[RetrievedPoint, ...],
        degradations: list[Degradation],
    ) -> tuple[_OrderedPoint, ...]:
        if not points:
            return ()
        top_n = self._policy.final_top_k
        documents = tuple(
            RerankDocument(
                id=point.sku, text=f"{point.name}\n{point.description}"
            )
            for point in points
        )
        by_sku = {point.sku: point for point in points}
        try:
            ranked = await self._reranker.rerank(query, documents, top_n=top_n)
        except RerankerUnavailable:
            degradations.append(Degradation("reranker", "unavailable"))
            return tuple((point, None) for point in points[:top_n])
        ordered: list[_OrderedPoint] = []
        for doc in ranked:
            point = by_sku.get(doc.id)
            if point is not None:
                ordered.append((point, doc.score))
        return tuple(ordered)

    async def _enrich(
        self,
        ordered: tuple[_OrderedPoint, ...],
        degradations: list[Degradation],
    ) -> tuple[RankedProduct, ...]:
        if not ordered:
            return ()
        skus = tuple(point.sku for point, _ in ordered)
        try:
            fetch = await self._catalog.get_products_by_skus(skus)
        except CatalogUnavailable:
            degradations.append(Degradation("catalog", "unavailable"))
            return tuple(
                self._from_point(point, score) for point, score in ordered
            )
        by_sku = {product.sku: product for product in fetch.products}
        missing = set(fetch.missing_skus)
        products: list[RankedProduct] = []
        for point, score in ordered:
            if point.sku in missing:
                continue
            authoritative = by_sku.get(point.sku)
            if authoritative is None:
                continue
            products.append(self._from_catalog(authoritative, point, score))
        return tuple(products)

    @staticmethod
    def _from_catalog(
        product: CatalogProduct,
        point: RetrievedPoint,
        score: Decimal | None,
    ) -> RankedProduct:
        return RankedProduct(
            sku=product.sku,
            name=product.name,
            category=product.category,
            snippet=point.description,
            price=product.price,
            stock=product.stock,
            in_stock=product.is_in_stock,
            margin_percent=product.margin_percent,
            rerank_score=score,
            price_authoritative=True,
        )

    @staticmethod
    def _from_point(
        point: RetrievedPoint, score: Decimal | None
    ) -> RankedProduct:
        price = (
            Money.of(point.price, Currency(point.currency))
            if point.price is not None
            else None
        )
        return RankedProduct(
            sku=point.sku,
            name=point.name,
            category=point.category,
            snippet=point.description,
            price=price,
            stock=point.stock,
            in_stock=point.in_stock,
            margin_percent=point.margin_percent,
            rerank_score=score,
            price_authoritative=False,
        )

    @staticmethod
    def _build_citations(
        products: tuple[RankedProduct, ...], *, now: datetime
    ) -> tuple[Citation, ...]:
        return tuple(
            Citation(
                source_type=CitationType.PRODUCT,
                ref=product.sku,
                title=product.name,
                snippet=product.snippet,
                position=index,
                retrieved_at=now,
                score=product.rerank_score,
            )
            for index, product in enumerate(products)
        )
