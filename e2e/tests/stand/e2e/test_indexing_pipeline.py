"""Сквозной конвейер: каталог → outbox → RabbitMQ → indexing → embedding →
RabbitMQ → indexing → Qdrant → RAG.

Ни один шаг не подменён: векторы считает реальная BGE-M3, сообщения идут через
реальный брокер, точки в Qdrant пишет только конвейер. Тесты наблюдают за
результатом через публичные контракты и ждут, а не спят фиксировано.
"""

import pytest

from tests.support.stand import (
    Catalog,
    Qdrant,
    Stand,
    ask,
    citation_refs,
    indexed_point,
    unique_suffix,
    wait_until,
)

pytestmark = pytest.mark.e2e


def _new_product(catalog: Catalog, suffix: str, **over: object) -> dict:
    """Товар с уникальными артикулом, названием и категорией."""
    fields: dict = {
        "sku": f"E2E-{suffix}",
        "name": f"Гарнитура {suffix}",
        "description": f"Беспроводная гарнитура серии {suffix}.",
        "category": f"E2ECAT-{suffix}",
    }
    fields.update(over)
    created = catalog.create(**fields)
    return {**created, **fields}


def test_created_product_appears_in_rag(
    catalog: Catalog, qdrant: Qdrant, stand: Stand, http
) -> None:
    """Созданный товар доезжает до Qdrant и находится агентом."""
    suffix = unique_suffix()
    product = _new_product(catalog, suffix)

    point = indexed_point(qdrant, product["id"])
    payload = point["payload"]
    assert payload["sku"] == product["sku"]
    assert payload["is_deleted"] is False
    assert len(point["vector"]["dense"]) == 1024
    assert point["vector"]["sparse"]["indices"]

    answer = ask(http, stand.agent, f"найди {product['name']}")

    # Формулировку ответа задаёт модель — проверяем цитату: она и есть
    # доказательство, что товар доехал до поисковой выдачи.
    assert "product_catalog_rag" in answer["used_tools"]
    assert product["sku"] in citation_refs(answer, "product")
    assert answer["degradations"] == []
    assert answer["confidence"] == "high"


def test_content_change_triggers_reindex(
    catalog: Catalog, qdrant: Qdrant
) -> None:
    """Новое описание пересчитывает векторы и водяной знак текста."""
    suffix = unique_suffix()
    product = _new_product(catalog, suffix)
    before = indexed_point(qdrant, product["id"])

    catalog.update_content(
        product["id"],
        product["version"],
        description=f"Полностью иное описание товара {suffix}: "
        "проводная модель для студийной записи.",
    )

    after = wait_until(
        lambda: (
            point
            if (point := qdrant.point(product["id"]))
            and (point["payload"].get("content_hash"))
            not in (None, before["payload"]["content_hash"])
            else None
        ),
        what="новый content_hash после смены описания",
    )

    assert after["payload"]["aggregate_version"] == 2
    assert after["vector"]["dense"] != before["vector"]["dense"]
    assert "студийной" in after["payload"]["description"]


def test_price_and_stock_change_keeps_embeddings(
    catalog: Catalog, qdrant: Qdrant
) -> None:
    """Смена цены и остатка не трогает векторы: текст не изменился."""
    suffix = unique_suffix()
    product = _new_product(catalog, suffix)
    before = indexed_point(qdrant, product["id"])

    updated = catalog.update_commercial(
        product["id"], product["version"], price="777.00"
    )
    catalog.set_stock(product["id"], updated["version"], stock=0)

    after = wait_until(
        lambda: (
            point
            if (point := qdrant.point(product["id"]))
            and point["payload"].get("price") == 777.0
            and point["payload"].get("stock") == 0
            else None
        ),
        what="новые цена и остаток в payload",
    )

    assert after["payload"]["in_stock"] is False
    assert after["payload"]["content_hash"] == before["payload"]["content_hash"]
    assert (
        after["payload"]["model_version"] == before["payload"]["model_version"]
    )
    assert after["vector"]["dense"] == before["vector"]["dense"]
    assert after["vector"]["sparse"] == before["vector"]["sparse"]


def test_deleted_product_disappears_from_search(
    catalog: Catalog, qdrant: Qdrant, stand: Stand, http
) -> None:
    """Удалённый товар помечается tombstone и уходит из выдачи RAG."""
    suffix = unique_suffix()
    product = _new_product(catalog, suffix)
    indexed_point(qdrant, product["id"])
    question = f"найди {product['name']}"

    found = ask(http, stand.agent, question)
    assert product["sku"] in citation_refs(found, "product")

    catalog.delete(product["id"], product["version"])

    tombstoned = wait_until(
        lambda: (
            point
            if (point := qdrant.point(product["id"]))
            and point["payload"].get("is_deleted") is True
            else None
        ),
        what="tombstone удалённого товара",
    )
    assert tombstoned["payload"]["aggregate_version"] == 2

    gone = ask(http, stand.agent, question)
    assert product["sku"] not in citation_refs(gone, "product")
