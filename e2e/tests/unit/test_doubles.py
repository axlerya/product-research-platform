"""Тесты детерминированных провайдеров стенда."""

import json

from fastapi.testclient import TestClient

from doubles.app import create_app
from doubles.llm import (
    PRICE_TOOL,
    RAG_TOOL,
    WEB_TOOL,
    build_completion,
    compose_answer,
    extract_category,
    plan_tool_calls,
)
from doubles.web import search_response


def _names(calls: list[dict]) -> list[str]:
    return [call["function"]["name"] for call in calls]


def _args(call: dict) -> dict:
    return json.loads(call["function"]["arguments"])


def test_plan_defaults_to_catalog_rag():
    """Запрос без маркеров уходит в поиск по каталогу."""
    calls = plan_tool_calls("что там по беспроводным наушникам")
    assert _names(calls) == [RAG_TOOL]
    assert _args(calls[0])["query"] == "что там по беспроводным наушникам"


def test_plan_routes_price_marker_to_price_analysis():
    """Маркер маржинальности выбирает только ценовой анализ."""
    calls = plan_tool_calls("оцени маржинальность")
    assert _names(calls) == [PRICE_TOOL]
    assert _args(calls[0])["bands"][0]["label"] == "низкая"


def test_plan_routes_web_marker_to_web_search():
    """Маркер рынка выбирает только веб-поиск."""
    calls = plan_tool_calls("что нового на рынке аудио")
    assert _names(calls) == [WEB_TOOL]
    assert _args(calls[0])["k"] == 3


def test_plan_combines_several_tools_in_one_turn():
    """Несколько маркеров дают несколько вызовов одним сообщением."""
    calls = plan_tool_calls(
        "найди товары, посчитай маржинальность и глянь рынок"
    )
    assert _names(calls) == [RAG_TOOL, PRICE_TOOL, WEB_TOOL]
    assert [call["id"] for call in calls] == ["call_1", "call_2", "call_3"]


def test_plan_passes_category_to_both_tools():
    """Категория из запроса сужает и поиск, и ценовой срез."""
    calls = plan_tool_calls(
        "покажи товары и маржинальность, категория Аудиотехника"
    )
    assert _args(calls[0])["category"] == "Аудиотехника"
    assert _args(calls[1])["category"] == "Аудиотехника"


def test_extract_category_returns_none_without_marker():
    """Без слова «категория» категория не выдумывается."""
    assert extract_category("найди наушники") is None


def test_compose_answer_lists_skus_and_degradations():
    """Ответ по каталогу перечисляет артикулы и деградации."""
    message = {
        "role": "tool",
        "name": RAG_TOOL,
        "content": json.dumps(
            {
                "products": [{"sku": "PROD-1"}, {"sku": "PROD-2"}],
                "degraded": ["reranker"],
            }
        ),
    }
    answer = compose_answer([message])
    assert "PROD-1, PROD-2" in answer
    assert "reranker" in answer


def test_compose_answer_quotes_price_analysis_ref():
    """Ответ ценового анализа несёт analysis_ref и медиану."""
    message = {
        "role": "tool",
        "name": PRICE_TOOL,
        "content": json.dumps(
            {
                "count": 3,
                "currency": "RUB",
                "analysis_ref": "pa-abc",
                "price": {"median": "100.00"},
            }
        ),
    }
    answer = compose_answer([message])
    assert "pa-abc" in answer
    assert "100.00" in answer


def test_compose_answer_lists_web_urls():
    """Ответ веб-поиска перечисляет ссылки из результатов."""
    message = {
        "role": "tool",
        "name": WEB_TOOL,
        "content": json.dumps(
            {"results": [{"url": "https://example.test/a/1"}]}
        ),
    }
    assert "https://example.test/a/1" in compose_answer([message])


def test_compose_answer_reports_tool_failure():
    """Отказ инструмента попадает в ответ честно, а не замалчивается."""
    message = {
        "role": "tool",
        "name": PRICE_TOOL,
        "content": json.dumps({"error": "tool_failed", "detail": "нет связи"}),
    }
    assert "отказал" in compose_answer([message])


def test_compose_answer_without_tools_says_so():
    """Пустой набор наблюдений не превращается в выдуманный ответ."""
    assert compose_answer([]) == "Инструменты не вернули данных."


def test_build_completion_plans_tools_on_first_turn():
    """Первый проход возвращает tool_calls и finish_reason=tool_calls."""
    body = build_completion(
        {
            "model": "m",
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "найди наушники"},
            ],
        }
    )
    choice = body["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    assert _names(choice["message"]["tool_calls"]) == [RAG_TOOL]
    assert body["usage"]["total_tokens"] == 24


def test_build_completion_answers_after_tool_messages():
    """После сообщений роли tool модель отвечает текстом."""
    body = build_completion(
        {
            "model": "m",
            "messages": [
                {"role": "user", "content": "найди наушники"},
                {"role": "assistant", "content": None},
                {
                    "role": "tool",
                    "name": RAG_TOOL,
                    "content": json.dumps({"products": [{"sku": "PROD-7"}]}),
                },
            ],
        }
    )
    choice = body["choices"][0]
    assert choice["finish_reason"] == "stop"
    assert "PROD-7" in choice["message"]["content"]
    assert "tool_calls" not in choice["message"]


def test_search_response_is_deterministic_and_bounded():
    """Веб-ответ воспроизводим и ограничен запрошенным k."""
    first = search_response("наушники", 3)
    second = search_response("наушники", 3)
    assert first == second
    assert len(first["results"]) == 3
    assert first["results"][0]["url"].startswith("https://example.test/")


def test_search_response_differs_between_queries():
    """Разные запросы дают разные ссылки (иначе цитаты неразличимы)."""
    a = search_response("наушники", 1)["results"][0]["url"]
    b = search_response("клавиатуры", 1)["results"][0]["url"]
    assert a != b


def test_search_response_clamps_to_bounds():
    """Запрос сверх лимита усечён, отрицательный — пустой список."""
    assert len(search_response("q", 50)["results"]) == 10
    assert search_response("q", -1)["results"] == []


def test_http_chat_completions_endpoint():
    """HTTP-контракт LLM: OpenAI-совместимый ответ."""
    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "deterministic-test-llm",
            "messages": [{"role": "user", "content": "найди наушники"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["finish_reason"] == "tool_calls"


def test_http_search_endpoint_matches_tavily_shape():
    """HTTP-контракт web-поиска: поля Tavily (results/content/url)."""
    client = TestClient(create_app())
    response = client.post(
        "/search", json={"api_key": "k", "query": "рынок", "max_results": 2}
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert set(results[0]) == {"title", "url", "content", "published_date"}


def test_http_health_endpoint():
    """Liveness отвечает для healthcheck compose."""
    assert TestClient(create_app()).get("/health").json() == {"status": "ok"}
