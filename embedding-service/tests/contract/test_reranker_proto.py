"""Contract-тесты Protobuf reranker: структура сервиса/сообщений + round-trip.

Отдельный пакет ``reranker.v1`` — не пересекается с ``embedding.v1``. Удаление
/ переименование поля или метода красит тест (лёгкий аналог buf breaking).
"""

import pytest
from google.protobuf.descriptor import FieldDescriptor

from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2_grpc as rpc,
)

pytestmark = pytest.mark.contract


def test_package_is_v1() -> None:
    assert pb.DESCRIPTOR.package == "reranker.v1"


def test_service_methods() -> None:
    service = pb.DESCRIPTOR.services_by_name["RerankerService"]
    assert set(service.methods_by_name) == {"Rerank"}


def test_message_fields() -> None:
    fields = {
        "RerankDocument": {"id", "text"},
        "RerankRequest": {"query", "documents", "top_n", "return_documents"},
        "RankedDocument": {"id", "index", "score", "text"},
        "RerankResponse": {"results", "model_version"},
    }
    for name, expected in fields.items():
        descriptor = getattr(pb, name).DESCRIPTOR
        assert set(descriptor.fields_by_name) == expected


def test_score_is_double() -> None:
    field = pb.RankedDocument.DESCRIPTOR.fields_by_name["score"]
    assert field.type == FieldDescriptor.TYPE_DOUBLE


def test_index_is_uint32() -> None:
    field = pb.RankedDocument.DESCRIPTOR.fields_by_name["index"]
    assert field.type == FieldDescriptor.TYPE_UINT32


def test_top_n_is_optional_uint32() -> None:
    field = pb.RerankRequest.DESCRIPTOR.fields_by_name["top_n"]
    assert field.type == FieldDescriptor.TYPE_UINT32
    # optional (proto3 presence): не задан → HasField == False.
    assert field.has_presence
    assert not pb.RerankRequest().HasField("top_n")


def test_documents_are_repeated() -> None:
    # upb-бэкенд (protobuf 5.x) не даёт FieldDescriptor.label — проверяем
    # repeated по конструкции (принимает несколько значений).
    request = pb.RerankRequest(
        documents=[
            pb.RerankDocument(id="a", text="x"),
            pb.RerankDocument(id="b", text="y"),
        ]
    )
    assert len(request.documents) == 2


def test_round_trip_preserves_shape() -> None:
    response = pb.RerankResponse(
        results=[
            pb.RankedDocument(id="d1", index=2, score=0.87, text="t"),
            pb.RankedDocument(id="d2", index=0, score=0.12),
        ],
        model_version="BAAI/bge-reranker-v2-m3@unknown|norm=1",
    )
    parsed = pb.RerankResponse.FromString(response.SerializeToString())
    assert [r.id for r in parsed.results] == ["d1", "d2"]
    assert parsed.results[0].index == 2
    assert parsed.results[0].score == pytest.approx(0.87)
    assert parsed.model_version.endswith("|norm=1")


def test_grpc_stubs_present() -> None:
    assert hasattr(rpc, "RerankerServiceServicer")
    assert hasattr(rpc, "RerankerServiceStub")
    assert hasattr(rpc, "add_RerankerServiceServicer_to_server")
