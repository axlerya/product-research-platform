"""Тесты контракта retrieval-портов (Protocol определён с методами)."""

from research_agent_service.application.ports.catalog import CatalogPort
from research_agent_service.application.ports.embedding import EmbeddingPort
from research_agent_service.application.ports.reranker import RerankerPort
from research_agent_service.application.ports.vector_search import (
    VectorSearchPort,
)


def test_ports_expose_expected_methods() -> None:
    """Порты определяют ожидаемые методы retrieval-пайплайна."""
    assert hasattr(EmbeddingPort, "embed_query")
    assert hasattr(VectorSearchPort, "hybrid_search")
    assert hasattr(RerankerPort, "rerank")
    assert hasattr(CatalogPort, "get_products_by_skus")
    assert hasattr(CatalogPort, "analyze_prices")
