"""Детерминированный web-провайдер стенда (формат ответа Tavily).

Внешний поиск заменён тестовым провайдером: сеть в сквозном сценарии дала бы
недетерминированный результат. Формат ответа — тот же, что у Tavily, поэтому
research-agent работает своим боевым адаптером, а не заглушкой.
"""

import hashlib
from typing import Any

MAX_RESULTS = 10


def _slug(query: str) -> str:
    """Стабильный url-безопасный ключ запроса."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def search_response(query: str, k: int) -> dict[str, Any]:
    """Возвращает ``k`` детерминированных результатов по запросу."""
    count = max(0, min(k, MAX_RESULTS))
    slug = _slug(query)
    return {
        "query": query,
        "results": [
            {
                "title": f"Рыночный обзор {index}: {query}",
                "url": f"https://example.test/{slug}/{index}",
                "content": (
                    f"Детерминированный фрагмент {index} по запросу «{query}»."
                ),
                "published_date": f"2026-01-{index:02d}",
            }
            for index in range(1, count + 1)
        ],
    }
