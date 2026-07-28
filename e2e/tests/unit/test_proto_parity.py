"""Паритет protobuf-контрактов между владельцем и потребителем.

embedding-service владеет контрактами ``embedding.v1`` и ``reranker.v1``;
research-agent-service держит их копию, из которой генерирует свои стабы.
Расхождение копий — источник несовместимости, которую не поймает ни один
unit-тест внутри сервиса.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

_ROOT = Path(__file__).resolve().parents[3]
_OWNER = _ROOT / "embedding-service" / "contracts" / "proto"
_CONSUMER = _ROOT / "research-agent-service" / "contracts" / "proto"


@pytest.mark.parametrize(
    "relative",
    ["embedding/v1/embedding.proto", "reranker/v1/reranker.proto"],
)
def test_proto_copies_are_identical(relative: str) -> None:
    """Копия контракта у потребителя совпадает с оригиналом владельца."""
    owner = (_OWNER / relative).read_bytes()
    consumer = (_CONSUMER / relative).read_bytes()

    assert owner == consumer
