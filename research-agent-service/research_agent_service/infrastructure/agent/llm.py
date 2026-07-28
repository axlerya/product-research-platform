"""LLM-адаптер: ChatOpenAI на OpenAI-совместимом эндпоинте (кастомный URL)."""

from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from research_agent_service.infrastructure.config import LlmSettings


def _extra_body(settings: LlmSettings) -> dict[str, Any]:
    """Собирает нестандартные поля запроса — только заданные явно.

    ``service_tier`` — расширение OpenAI, ``chat_template_kwargs`` — vLLM и
    совместимых. Сторонний провайдер вправе отвергнуть незнакомое поле, и
    тогда падал бы каждый вызов, поэтому по умолчанию не отправляем ничего.
    """
    body: dict[str, Any] = {}
    if settings.service_tier:
        body["service_tier"] = settings.service_tier
    if settings.enable_thinking is not None:
        body["chat_template_kwargs"] = {
            "enable_thinking": settings.enable_thinking
        }
    return body


def build_chat_model(settings: LlmSettings) -> ChatOpenAI:
    """Строит ChatOpenAI, указывающий на кастомный base_url.

    Провайдер — любой OpenAI-совместимый: self-hosted, DeepInfra и прочие.
    """
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=SecretStr(settings.api_key),
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        extra_body=_extra_body(settings),
    )
