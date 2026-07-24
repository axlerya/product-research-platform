"""Контейнер прикладных сервисов для HTTP-слоя.

Приложение хранит его в app.state; маршруты получают через зависимость.
readiness — асинхронная проба готовности зависимостей для GET /ready.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from research_agent_service.application.use_cases.answer_query import (
    AnswerQueryUseCase,
)
from research_agent_service.application.use_cases.read_queries import (
    GetQueryUseCase,
    ListQueriesUseCase,
)
from research_agent_service.application.use_cases.submit_feedback import (
    SubmitFeedbackUseCase,
)

ReadinessProbe = Callable[[], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ApiServices:
    """Use cases и проба готовности, доступные маршрутам."""

    answer_query: AnswerQueryUseCase
    submit_feedback: SubmitFeedbackUseCase
    list_queries: ListQueriesUseCase
    get_query: GetQueryUseCase
    readiness: ReadinessProbe
