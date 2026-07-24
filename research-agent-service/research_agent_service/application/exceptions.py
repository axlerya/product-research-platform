"""Прикладные исключения — сигналы деградации и ошибки сценариев."""

from research_agent_service.domain.value_objects.identifiers import AgentRunId


class ApplicationError(Exception):
    """Базовое прикладное исключение."""


class UnknownAgentRun(ApplicationError):
    """Обратная связь/оценка ссылается на несуществующий прогон."""


class RateLimited(ApplicationError):
    """Превышен лимит частоты запросов клиента."""

    def __init__(self, *, retry_after_s: float | None = None) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_s = retry_after_s


class QueryFailed(ApplicationError):
    """Прогон завершился ошибкой; событие agent.query.failed.v1 записано."""

    def __init__(self, run_id: AgentRunId) -> None:
        super().__init__(str(run_id.value))
        self.run_id = run_id


class RerankerUnavailable(ApplicationError):
    """Reranker недоступен — retrieval деградирует до порядка RRF."""


class CatalogUnavailable(ApplicationError):
    """catalog-service недоступен — цены берём из read-model с пометкой."""
