"""Схемы POST /query: запрос и ответ."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from research_agent_service.application.dto.answer import AnswerQueryCommand
from research_agent_service.domain.value_objects.enums import (
    Confidence,
    RunStatus,
)
from research_agent_service.domain.value_objects.identifiers import (
    ConversationId,
)
from research_agent_service.domain.value_objects.query import (
    MAX_QUERY_CHARS,
    Query,
    QueryFilters,
)
from research_agent_service.presentation.schemas.common import (
    CitationSchema,
    DegradationSchema,
    UsageSchema,
)


class QueryFiltersSchema(BaseModel):
    """Безопасные фасеты запроса (только индексируемые поля)."""

    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    brand: str | None = None
    supplier: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock: bool | None = None
    min_rating: Decimal | None = None
    margin_min: Decimal | None = None
    margin_max: Decimal | None = None

    def to_domain(self) -> QueryFilters:
        """Переводит в доменные QueryFilters (валидирует диапазоны)."""
        return QueryFilters(
            category=self.category,
            brand=self.brand,
            supplier=self.supplier,
            price_min=self.price_min,
            price_max=self.price_max,
            in_stock=self.in_stock,
            min_rating=self.min_rating,
            margin_min=self.margin_min,
            margin_max=self.margin_max,
        )


class QueryRequest(BaseModel):
    """Тело POST /query."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    locale: str = "ru"
    conversation_id: UUID | None = None
    idempotency_key: str | None = None
    filters: QueryFiltersSchema | None = None

    def to_command(
        self,
        *,
        client_principal: str,
        trace_id: str | None,
        correlation_id: str | None,
    ) -> AnswerQueryCommand:
        """Строит команду use case (валидирует запрос доменом)."""
        query = Query(
            text=self.text,
            locale=self.locale,
            filters=self.filters.to_domain() if self.filters else None,
            idempotency_key=self.idempotency_key,
        )
        return AnswerQueryCommand(
            query=query,
            client_principal=client_principal,
            conversation_id=(
                ConversationId(self.conversation_id)
                if self.conversation_id is not None
                else None
            ),
            trace_id=trace_id,
            correlation_id=correlation_id,
        )


class QueryResponse(BaseModel):
    """Ответ POST /query."""

    agent_run_id: UUID
    conversation_id: UUID
    status: RunStatus
    answer: str
    citations: list[CitationSchema]
    used_tools: list[str]
    confidence: Confidence | None
    degradations: list[DegradationSchema]
    usage: UsageSchema
    latency_ms: int
