"""Use case ``RerankDocuments`` — синхронное ранжирование (fail-fast).

Валидация входа → ``ValidationError`` (fail-fast транспорта, как у запросов);
дефект инференса (несовпадение числа скоров, не-конечный скор) →
``InferenceError``. Провайдер сам поднимает транзиентные ошибки инференса.
"""

from collections.abc import Sequence

from embedding_service.application.dto.reranking import RerankDocumentsCommand
from embedding_service.application.exceptions import (
    InferenceError,
    ValidationError,
)
from embedding_service.application.ports.reranker_provider import (
    RerankerProvider,
)
from embedding_service.domain.exceptions import DomainError
from embedding_service.domain.services.reranking.top_n_selector import (
    TopNSelector,
)
from embedding_service.domain.services.reranking.validator import (
    RerankValidator,
)
from embedding_service.domain.value_objects.reranking.candidate import (
    RerankCandidate,
)
from embedding_service.domain.value_objects.reranking.limits import (
    RerankLimits,
)
from embedding_service.domain.value_objects.reranking.query import RerankQuery
from embedding_service.domain.value_objects.reranking.ranked_item import (
    RankedItem,
)
from embedding_service.domain.value_objects.reranking.relevance_score import (
    RelevanceScore,
)
from embedding_service.domain.value_objects.reranking.result import (
    RerankResult,
)
from embedding_service.domain.value_objects.reranking.top_n import TopN
from embedding_service.domain.value_objects.text_id import TextId


class RerankDocuments:
    """Ранжирует документы относительно запроса; невалидный вход — fail-fast."""

    def __init__(
        self, provider: RerankerProvider, limits: RerankLimits
    ) -> None:
        self._provider = provider
        self._limits = limits

    async def handle(self, command: RerankDocumentsCommand) -> RerankResult:
        query, candidates, top_n = self._to_domain(command)
        scores = await self._provider.rerank(
            query.value, [candidate.text for candidate in candidates]
        )
        items = self._assemble(candidates, scores)
        ranked = TopNSelector.select(items, top_n)
        return RerankResult(model_id=self._provider.model_id, items=ranked)

    def _to_domain(
        self, command: RerankDocumentsCommand
    ) -> tuple[RerankQuery, tuple[RerankCandidate, ...], TopN | None]:
        """Строит и валидирует доменные VO; любой дефект входа → fail-fast.

        Все доменные ошибки этой фазы — клиентские (пустой текст, лимиты,
        некорректный ``top_n``), поэтому единообразно → ``ValidationError``.
        Не через ``to_application_error``: ``InvalidTopNError`` не в наборе
        валидаций и был бы ошибочно отнесён к транзиенту.
        """
        try:
            query = RerankQuery(command.query)
            candidates = tuple(
                RerankCandidate(TextId(doc.text_id), doc.text)
                for doc in command.documents
            )
            top_n = TopN(command.top_n) if command.top_n is not None else None
            RerankValidator.validate(query, candidates, self._limits)
        except DomainError as exc:
            raise ValidationError(
                str(exc), domain_type=type(exc).__name__
            ) from exc
        return query, candidates, top_n

    def _assemble(
        self,
        candidates: Sequence[RerankCandidate],
        scores: Sequence[float],
    ) -> tuple[RankedItem, ...]:
        """Собирает ранжируемые элементы; дефект выхода модели → transient."""
        if len(scores) != len(candidates):
            raise InferenceError(
                f"reranker вернул {len(scores)} скоров "
                f"для {len(candidates)} документов"
            )
        try:
            return tuple(
                RankedItem(candidate.text_id, index, RelevanceScore(score))
                for index, (candidate, score) in enumerate(
                    zip(candidates, scores, strict=True)
                )
            )
        except DomainError as exc:
            raise InferenceError(str(exc)) from exc
