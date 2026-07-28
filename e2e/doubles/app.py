"""ASGI-приложение тестовых провайдеров стенда: LLM и web-поиск.

Один процесс отдаёт два внешних контракта, которые в стенде заменены
детерминированными: OpenAI-совместимый ``/v1/chat/completions`` и
Tavily-совместимый ``/search``. Всё остальное в стенде — боевые сервисы.
"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from doubles.llm import build_completion
from doubles.web import search_response


class SearchRequest(BaseModel):
    """Запрос web-поиска в формате Tavily."""

    model_config = ConfigDict(extra="ignore")

    query: str
    max_results: int = Field(default=5, ge=0)
    api_key: str | None = None


def create_app() -> FastAPI:
    """Собирает приложение тестовых провайдеров."""
    app = FastAPI(title="platform-test-doubles")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness стенда."""
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(body: dict[str, Any]) -> dict[str, Any]:
        """OpenAI-совместимый ответ: план инструментов либо финальный текст."""
        return build_completion(body)

    @app.post("/search")
    async def search(body: SearchRequest) -> dict[str, Any]:
        """Tavily-совместимый ответ детерминированного web-поиска."""
        return search_response(body.query, body.max_results)

    return app


app = create_app()
