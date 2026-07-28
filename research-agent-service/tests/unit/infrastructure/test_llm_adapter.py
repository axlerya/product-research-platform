"""Тесты LLM-адаптера (построение ChatOpenAI без сетевых вызовов)."""

from langchain_openai import ChatOpenAI

from research_agent_service.infrastructure.agent.llm import build_chat_model
from research_agent_service.infrastructure.config import LlmSettings


def test_build_chat_model_uses_config() -> None:
    """Фабрика пробрасывает base_url, модель и extra_body из настроек."""
    settings = LlmSettings(
        model="qwen3",
        base_url="http://llm:8001/v1",
        api_key="k",
        temperature=0.2,
        max_tokens=1024,
        service_tier="priority",
        enable_thinking=True,
    )

    model = build_chat_model(settings)

    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "qwen3"
    assert str(model.openai_api_base) == "http://llm:8001/v1"
    assert model.temperature == 0.2
    assert model.max_tokens == 1024
    assert model.extra_body["service_tier"] == "priority"
    assert model.extra_body["chat_template_kwargs"]["enable_thinking"] is True


def test_provider_specific_fields_are_omitted_when_not_configured() -> None:
    """Незаданные поля не отправляются вовсе.

    ``service_tier`` — расширение OpenAI, ``chat_template_kwargs`` — vLLM.
    Сторонние OpenAI-совместимые провайдеры могут отвергнуть незнакомое поле,
    и тогда падал бы каждый вызов. Отправляем только то, что задано явно.
    """
    model = build_chat_model(LlmSettings(base_url="https://api/v1"))

    assert not model.extra_body


def test_thinking_flag_is_sent_when_set_explicitly() -> None:
    """Явно выключенный thinking — это тоже значение, его надо передать."""
    model = build_chat_model(
        LlmSettings(base_url="https://api/v1", enable_thinking=False)
    )

    assert model.extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_service_tier_alone_does_not_add_template_kwargs() -> None:
    """Поля независимы: заданное одно не тянет за собой другое."""
    model = build_chat_model(
        LlmSettings(base_url="https://api/v1", service_tier="auto")
    )

    assert model.extra_body == {"service_tier": "auto"}
