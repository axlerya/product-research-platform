"""Детерминированный OpenAI-совместимый LLM для стенда.

Модель заменяется тестовым провайдером сознательно: сквозной сценарий
проверяет конвейер платформы, а не качество генерации. Поведение обязано быть
воспроизводимым, поэтому план вызовов инструментов выводится из текста
запроса по фиксированным маркерам, а финальный ответ собирается из того, что
реально вернули инструменты (никаких выдуманных SKU и ссылок).
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

RAG_TOOL = "product_catalog_rag"
PRICE_TOOL = "price_analysis"
WEB_TOOL = "web_search"

# Маркеры намерения. «ценов» вместо «цен» намеренно: «цен» встречается внутри
# слова «оцени» и цеплял бы ценовой анализ там, где его не просили.
_RAG_MARKERS = ("найди", "подбер", "товар", "каталог", "покажи")
_PRICE_MARKERS = ("маржин", "ценов", "стоимост", "прайс")
_WEB_MARKERS = ("рынк", "рынок", "интернет", "обзор", "новост")

_CATEGORY_MARKERS = ("категория", "категории")
_WEB_RESULTS = 3
_BANDS = (
    {"label": "низкая", "upper_percent": "30"},
    {"label": "высокая", "lower_percent": "30"},
)


def _matches(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def extract_category(text: str) -> str | None:
    """Категория из запроса: слово после «категория»/«категории».

    Единственная структура, которую понимает стенд: она позволяет сузить срез
    ценового анализа до товаров конкретного теста, не изобретая скрытых полей.
    """
    tokens = text.replace(",", " ").replace(".", " ").split()
    lowered = [token.lower() for token in tokens]
    for index, token in enumerate(lowered[:-1]):
        if token in _CATEGORY_MARKERS:
            return tokens[index + 1]
    return None


def plan_tool_calls(user_text: str) -> list[dict[str, Any]]:
    """Строит список вызовов инструментов по тексту запроса."""
    lowered = user_text.lower()
    category = extract_category(user_text)
    planned: list[tuple[str, dict[str, Any]]] = []
    if _matches(lowered, _RAG_MARKERS):
        planned.append((RAG_TOOL, _rag_args(user_text, category)))
    if _matches(lowered, _PRICE_MARKERS):
        planned.append((PRICE_TOOL, _price_args(category)))
    if _matches(lowered, _WEB_MARKERS):
        planned.append((WEB_TOOL, {"query": user_text, "k": _WEB_RESULTS}))
    if not planned:
        planned.append((RAG_TOOL, _rag_args(user_text, category)))
    return [
        {
            "id": f"call_{index}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        for index, (name, args) in enumerate(planned, start=1)
    ]


def _rag_args(user_text: str, category: str | None) -> dict[str, Any]:
    args: dict[str, Any] = {"query": user_text}
    if category is not None:
        args["category"] = category
    return args


def _price_args(category: str | None) -> dict[str, Any]:
    args: dict[str, Any] = {"bands": [dict(band) for band in _BANDS]}
    if category is not None:
        args["category"] = category
    return args


def _rag_summary(observation: Mapping[str, Any]) -> str | None:
    products = observation.get("products") or []
    degraded = observation.get("degraded") or []
    if not products:
        return "Товары не найдены."
    skus = ", ".join(str(item.get("sku", "")) for item in products)
    summary = f"Товары: {skus}."
    if degraded:
        summary += f" Деградации: {', '.join(str(d) for d in degraded)}."
    return summary


def _price_summary(observation: Mapping[str, Any]) -> str | None:
    price = observation.get("price") or {}
    return (
        f"Ценовой анализ {observation.get('analysis_ref')}: "
        f"{observation.get('count')} товаров, медиана "
        f"{price.get('median')} {observation.get('currency')}."
    )


def _web_summary(observation: Mapping[str, Any]) -> str | None:
    results = observation.get("results") or []
    if not results:
        return "Веб-источники не найдены."
    urls = ", ".join(str(item.get("url", "")) for item in results)
    return f"Источники: {urls}."


def compose_answer(tool_messages: Sequence[Mapping[str, Any]]) -> str:
    """Собирает ответ строго из наблюдений инструментов."""
    parts: list[str] = []
    for message in tool_messages:
        try:
            observation = json.loads(message.get("content") or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(observation, dict):
            continue
        summary = _summary_for(message.get("name"), observation)
        if summary is not None:
            parts.append(summary)
    return " ".join(parts) if parts else "Инструменты не вернули данных."


def _summary_for(
    name: str | None, observation: Mapping[str, Any]
) -> str | None:
    # Отказ проверяем до диспетчеризации по имени: упавший инструмент
    # возвращает {"error": ...} под своим же именем, и разбор его как
    # успешного наблюдения дал бы ответ из None вместо честного «отказал».
    error = observation.get("error")
    if error:
        return f"Инструмент {name} отказал: {error}."
    if name == RAG_TOOL:
        return _rag_summary(observation)
    if name == PRICE_TOOL:
        return _price_summary(observation)
    if name == WEB_TOOL:
        return _web_summary(observation)
    return None


def _last_user_text(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def build_completion(request: Mapping[str, Any]) -> dict[str, Any]:
    """Строит ответ ``/v1/chat/completions`` по истории сообщений.

    Есть сообщения роли ``tool`` — значит инструменты уже отработали и пора
    отвечать текстом; иначе планируем вызовы инструментов.
    """
    messages = list(request.get("messages") or [])
    model = str(request.get("model") or "deterministic-test-llm")
    tool_messages = [
        message for message in messages if message.get("role") == "tool"
    ]
    if tool_messages:
        return _completion(
            model,
            message={
                "role": "assistant",
                "content": compose_answer(tool_messages),
            },
            finish_reason="stop",
        )
    return _completion(
        model,
        message={
            "role": "assistant",
            "content": None,
            "tool_calls": plan_tool_calls(_last_user_text(messages)),
        },
        finish_reason="tool_calls",
    )


def _completion(
    model: str, *, message: Mapping[str, Any], finish_reason: str
) -> dict[str, Any]:
    """Конверт ChatCompletion с фиксированными id/временем (детерминизм)."""
    return {
        "id": "chatcmpl-deterministic",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": dict(message),
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 16,
            "completion_tokens": 8,
            "total_tokens": 24,
        },
    }
