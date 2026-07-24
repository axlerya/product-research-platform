"""Проверка источников ответа — provenance цитат (INV-2)."""

from collections.abc import Iterable

from research_agent_service.domain.value_objects.citation import Citation
from research_agent_service.domain.value_objects.enums import CitationType


class SourceValidator:
    """Отбрасывает «висячие» цитаты.

    INV-2 (provenance): ref цитаты обязан принадлежать множеству реально
    полученных фактов своего типа (sku для product, URL для web,
    analysis_ref для price_analysis). Проверяется подлинность ССЫЛКИ, а не
    достоверность утверждения — последнее закрывает отдельная числовая
    проверка (INV-6).
    """

    def validate(
        self,
        citations: Iterable[Citation],
        *,
        product_refs: frozenset[str],
        web_refs: frozenset[str],
        price_refs: frozenset[str],
    ) -> tuple[Citation, ...]:
        """Возвращает только цитаты с подтверждённым provenance."""
        allowed: dict[CitationType, frozenset[str]] = {
            CitationType.PRODUCT: product_refs,
            CitationType.WEB: web_refs,
            CitationType.PRICE_ANALYSIS: price_refs,
        }
        return tuple(
            citation
            for citation in citations
            if citation.ref in allowed[citation.source_type]
        )
