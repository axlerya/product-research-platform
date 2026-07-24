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
