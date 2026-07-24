"""Спецификации инструментов для bind_tools и разбор имени вызова.

Схемы аргументов берутся из pydantic-контрактов; имена — из закрытого
allowlist ToolName. Имя инструмента, пришедшее от модели, проверяется по
этому же allowlist — незнакомое имя не исполняется.
"""

from pydantic import BaseModel

from research_agent_service.domain.value_objects.enums import ToolName
from research_agent_service.infrastructure.agent.contracts import (
    PriceAnalysisArgs,
    ProductCatalogRagArgs,
    WebSearchArgs,
)

_DESCRIPTIONS: dict[ToolName, tuple[str, type[BaseModel]]] = {
    ToolName.PRODUCT_CATALOG_RAG: (
        "Поиск товаров в каталоге по запросу и безопасным фасетам.",
        ProductCatalogRagArgs,
    ),
    ToolName.PRICE_ANALYSIS: (
        "Детерминированный ценовой анализ: медиана, бэнды маржи, выбросы.",
        PriceAnalysisArgs,
    ),
    ToolName.WEB_SEARCH: (
        "Внешний веб-поиск для рыночного контекста.",
        WebSearchArgs,
    ),
}


def build_tool_specs() -> list[dict[str, object]]:
    """Список инструментов в OpenAI-формате для bind_tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.value,
                "description": description,
                "parameters": model.model_json_schema(),
            },
        }
        for tool, (description, model) in _DESCRIPTIONS.items()
    ]


def resolve_tool(name: str) -> ToolName | None:
    """Переводит имя вызова от модели в ToolName или None (незнакомое)."""
    try:
        return ToolName(name)
    except ValueError:
        return None
