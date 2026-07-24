"""LLM-адаптер: ChatOpenAI на OpenAI-совместимом эндпоинте (кастомный URL)."""

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from research_agent_service.infrastructure.config import LlmSettings


def build_chat_model(settings: LlmSettings) -> ChatOpenAI:
    """Строит ChatOpenAI, указывающий на кастомный base_url.

    Провайдер — OpenAI-совместимый (например self-hosted). ``extra_body``
    несёт service_tier и chat_template_kwargs (enable_thinking).
    """
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=SecretStr(settings.api_key),
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        extra_body={
            "service_tier": settings.service_tier,
            "chat_template_kwargs": {
                "enable_thinking": settings.enable_thinking,
            },
        },
    )
