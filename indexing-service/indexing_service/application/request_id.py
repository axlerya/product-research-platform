"""Детерминированный ``request_id`` команды на эмбеддинг (§9.1).

``request_id = uuid5(NS, "{job_id}|{attempt}|{sha(items)}")`` — один и тот же
для оригинала (``attempt=0``) и для каждого ретрая/rechunk. Повторная
публикация той же команды → тот же id → embedding-service дедупит, а наш apply
дедупит по ``request.status``. Это ключ всей идемпотентности плеча.
"""

import hashlib
from collections.abc import Sequence
from uuid import UUID, uuid5

from indexing_service.domain.entities.embedding_request import RequestItem
from indexing_service.domain.value_objects.identifiers import JobId, RequestId

# Стабильное пространство имён (не менять — иначе поедут все id).
_NAMESPACE = UUID("7f3b2c1d-4e5a-4b6c-8d9e-0a1b2c3d4e5f")

_SEP = "\x1f"


def _items_digest(items: Sequence[RequestItem]) -> str:
    payload = "\x1e".join(
        f"{item.text_id}{_SEP}{item.text}" for item in items
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_request_id(
    job_id: JobId, attempt: int, items: Sequence[RequestItem]
) -> RequestId:
    """Строит детерминированный ``RequestId`` по job/attempt/items."""
    name = f"{job_id.value}|{attempt}|{_items_digest(items)}"
    return RequestId(uuid5(_NAMESPACE, name))
