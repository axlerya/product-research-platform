"""Зависимости FastAPI: доступ к контейнеру сервисов из app.state."""

from fastapi import Request

from research_agent_service.presentation.api.services import ApiServices


def get_services(request: Request) -> ApiServices:
    """Возвращает контейнер прикладных сервисов приложения."""
    return request.app.state.services
