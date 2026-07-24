"""Общие схемы ответа: цитата, расход токенов, деградация, ошибка."""

from pydantic import BaseModel

from research_agent_service.domain.value_objects.enums import CitationType


class CitationSchema(BaseModel):
    """Источник факта в ответе (score — строкой, без float)."""

    source_type: CitationType
    ref: str
    title: str
    snippet: str
    position: int
    score: str | None = None


class UsageSchema(BaseModel):
    """Расход токенов LLM за прогон."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class DegradationSchema(BaseModel):
    """Деградация зависимости в прогоне."""

    dependency: str
    reason: str


class ErrorResponse(BaseModel):
    """Единый формат ошибки API."""

    error: str
    detail: str | None = None
