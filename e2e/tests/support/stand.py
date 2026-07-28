"""Работа с поднятым стендом: адреса, ожидания, клиенты по контрактам.

Тесты говорят со стендом только по его публичным контрактам: REST каталога и
агента, REST Qdrant (исключительно на чтение), management API RabbitMQ.
Ничего в Qdrant напрямую не пишется — точки туда обязан положить конвейер.
"""

import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

# Запас на загруженный стенд: при полном прогоне через конвейер проходит
# несколько десятков товаров, и на общей очереди отдельная проверка ждёт
# заметно дольше, чем в одиночку. Ожидание опросное — на быстром стенде
# запас ничего не стоит.
DEFAULT_TIMEOUT_S = 300.0
POLL_INTERVAL_S = 0.5


@dataclass(frozen=True, slots=True)
class Stand:
    """Адреса компонентов стенда (переопределяются окружением)."""

    catalog: str
    agent: str
    agent_degraded: str
    qdrant: str
    rabbit_management: str
    rabbit_user: str
    rabbit_password: str
    embedding_ops: str
    doubles: str
    collection: str

    @property
    def rabbit_auth(self) -> tuple[str, str]:
        """Доступ к management API брокера."""
        return (self.rabbit_user, self.rabbit_password)

    @classmethod
    def from_env(cls) -> "Stand":
        """Адреса стенда; по умолчанию — порты из корневого compose."""
        return cls(
            catalog=os.getenv("STAND_CATALOG_URL", "http://localhost:8001"),
            agent=os.getenv("STAND_AGENT_URL", "http://localhost:8080"),
            agent_degraded=os.getenv(
                "STAND_AGENT_DEGRADED_URL", "http://localhost:8081"
            ),
            qdrant=os.getenv("STAND_QDRANT_URL", "http://localhost:6333"),
            rabbit_management=os.getenv(
                "STAND_RABBITMQ_MANAGEMENT_URL", "http://localhost:15672"
            ),
            # Умолчания совпадают с .env.example: свои значения из .env
            # прокидываются в тесты этими же переменными.
            rabbit_user=os.getenv("RABBITMQ_USER", "platform"),
            rabbit_password=os.getenv(
                "RABBITMQ_PASSWORD", "change-me-rabbitmq"
            ),
            embedding_ops=os.getenv(
                "STAND_EMBEDDING_OPS_URL", "http://localhost:8010"
            ),
            doubles=os.getenv("STAND_DOUBLES_URL", "http://localhost:8090"),
            collection=os.getenv("STAND_QDRANT_COLLECTION", "products"),
        )


def wait_until(
    predicate: Callable[[], Any],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    what: str = "условие",
) -> Any:
    """Ждёт истинного результата предиката и возвращает его.

    Конвейер асинхронный (outbox → брокер → инференс → Qdrant), поэтому
    сквозные проверки опрашивают наблюдаемое состояние, а не спят фиксировано.
    """
    deadline = time.monotonic() + timeout_s
    last: Any = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval_s)
    raise AssertionError(f"Не дождались: {what} (последнее значение: {last!r})")


def unique_suffix() -> str:
    """Уникальный ASCII-суффикс для артикулов и категорий теста."""
    return uuid.uuid4().hex[:10].upper()


class Catalog:
    """Тонкий клиент API каталога для подготовки данных сценария."""

    def __init__(self, client: httpx.Client, base_url: str) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    def create(
        self,
        *,
        sku: str,
        name: str,
        description: str,
        category: str,
        brand: str = "E2EBrand",
        supplier: str = "E2ESupplier",
        price: str = "100.00",
        cost: str = "40.00",
        stock: int = 10,
    ) -> dict[str, Any]:
        """Создаёт товар и возвращает ``{id, sku, version}``."""
        response = self._client.post(
            f"{self._base}/api/v1/products",
            json={
                "sku": sku,
                "name": name,
                "description": description,
                "category": category,
                "brand": brand,
                "supplier": supplier,
                "price": price,
                "cost": cost,
                "stock": stock,
                "sales_per_month": 5,
                "avg_rating": "4.50",
                "review_count": 12,
            },
        )
        response.raise_for_status()
        return response.json()

    def update_content(
        self, product_id: str, version: int, **fields: Any
    ) -> dict[str, Any]:
        """Меняет контентные поля (порождает ре-эмбеддинг)."""
        return self._patch(f"/api/v1/products/{product_id}", version, fields)

    def update_commercial(
        self, product_id: str, version: int, **fields: Any
    ) -> dict[str, Any]:
        """Меняет цену/себестоимость/поставщика (без ре-эмбеддинга)."""
        return self._patch(
            f"/api/v1/products/{product_id}/commercial", version, fields
        )

    def set_stock(
        self, product_id: str, version: int, stock: int
    ) -> dict[str, Any]:
        """Устанавливает остаток (без ре-эмбеддинга)."""
        return self._patch(
            f"/api/v1/products/{product_id}/stock", version, {"stock": stock}
        )

    def delete(self, product_id: str, version: int) -> None:
        """Мягко удаляет товар."""
        response = self._client.delete(
            f"{self._base}/api/v1/products/{product_id}",
            headers={"If-Match": f'"{version}"'},
        )
        response.raise_for_status()

    def by_skus(
        self, skus: list[str], *, include_deleted: bool = False
    ) -> httpx.Response:
        """Batch-чтение по артикулам (контракт research-agent)."""
        return self._client.post(
            f"{self._base}/api/v1/products/by-skus",
            json={"skus": skus, "include_deleted": include_deleted},
        )

    def analyze_prices(
        self,
        selector: dict[str, Any],
        bands: list[dict[str, Any]] | None = None,
    ) -> httpx.Response:
        """Ценовой анализ среза (контракт research-agent)."""
        return self._client.post(
            f"{self._base}/api/v1/analytics/prices",
            json={"selector": selector, "bands": bands or []},
        )

    def _patch(
        self, path: str, version: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._client.patch(
            f"{self._base}{path}",
            json=payload,
            headers={"If-Match": f'"{version}"'},
        )
        response.raise_for_status()
        return response.json()


class Qdrant:
    """Read-only доступ к Qdrant: тесты только наблюдают за конвейером."""

    def __init__(
        self, client: httpx.Client, base_url: str, collection: str
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._collection = collection

    def point(self, point_id: str) -> dict[str, Any] | None:
        """Точка с payload и векторами или ``None``, если её ещё нет."""
        response = self._client.post(
            f"{self._base}/collections/{self._collection}/points",
            json={"ids": [point_id], "with_payload": True, "with_vector": True},
        )
        if response.status_code != 200:
            return None
        result = response.json().get("result") or []
        return result[0] if result else None

    def collection_info(self) -> dict[str, Any]:
        """Конфигурация коллекции (для контрактной проверки)."""
        response = self._client.get(
            f"{self._base}/collections/{self._collection}"
        )
        response.raise_for_status()
        return response.json()["result"]


def indexed_point(
    qdrant: Qdrant, point_id: str, *, timeout_s: float = DEFAULT_TIMEOUT_S
) -> dict[str, Any]:
    """Ждёт точку с посчитанными векторами и водяным знаком модели."""

    def _ready() -> dict[str, Any] | None:
        point = qdrant.point(point_id)
        if point is None:
            return None
        payload = point.get("payload") or {}
        vectors = point.get("vector") or {}
        if not payload.get("model_version"):
            return None
        if "dense" not in vectors or "sparse" not in vectors:
            return None
        return point

    return wait_until(
        _ready, timeout_s=timeout_s, what=f"векторы точки {point_id} в Qdrant"
    )


def ask(
    client: httpx.Client, base_url: str, text: str, **body: Any
) -> dict[str, Any]:
    """Задаёт вопрос агенту и возвращает разобранный ответ."""
    response = client.post(
        f"{base_url.rstrip('/')}/query", json={"text": text, **body}
    )
    response.raise_for_status()
    return response.json()


def citation_refs(answer: dict[str, Any], source_type: str) -> list[str]:
    """Ссылки цитат заданного типа из ответа агента."""
    return [
        citation["ref"]
        for citation in answer["citations"]
        if citation["source_type"] == source_type
    ]


def degradation_pairs(answer: dict[str, Any]) -> set[tuple[str, str]]:
    """Пары «зависимость → причина» из деградаций ответа."""
    return {
        (item["dependency"], item["reason"]) for item in answer["degradations"]
    }
