"""Contract-тесты Protobuf: структура сервиса/сообщений + round-trip.

Структурные проверки — лёгкий заменитель ``buf breaking`` в CI без buf:
удаление/переименование поля или метода красит тест.
"""

import pytest
from google.protobuf.descriptor import FieldDescriptor

from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc as rpc,
)

pytestmark = pytest.mark.contract


def test_package_is_v1() -> None:
    assert pb.DESCRIPTOR.package == "embedding.v1"


def test_service_methods() -> None:
    service = pb.DESCRIPTOR.services_by_name["EmbeddingService"]
    assert set(service.methods_by_name) == {"EmbedQuery", "EmbedQueries"}


def test_message_fields() -> None:
    fields = {
        "EmbedQueryRequest": {"text", "request_id"},
        "EmbedQueryResponse": {"embedding", "model_version", "dim"},
        "QueryEmbedding": {"dense", "sparse", "token_count"},
        "DenseVector": {"values"},
        "SparseVector": {"indices", "values"},
        "EmbedQueriesRequest": {"texts", "request_id"},
        "EmbedQueriesResponse": {"embeddings", "model_version", "dim"},
    }
    for name, expected in fields.items():
        descriptor = getattr(pb, name).DESCRIPTOR
        assert set(descriptor.fields_by_name) == expected


def test_dense_is_repeated_float() -> None:
    field = pb.DenseVector.DESCRIPTOR.fields_by_name["values"]
    assert field.type == FieldDescriptor.TYPE_FLOAT
    # repeated: принимает несколько значений
    assert len(pb.DenseVector(values=[1.0, 2.0, 3.0]).values) == 3


def test_sparse_indices_uint32() -> None:
    field = pb.SparseVector.DESCRIPTOR.fields_by_name["indices"]
    assert field.type == FieldDescriptor.TYPE_UINT32


def test_round_trip_preserves_shape() -> None:
    response = pb.EmbedQueryResponse(
        embedding=pb.QueryEmbedding(
            dense=pb.DenseVector(values=[0.1] * 1024),
            sparse=pb.SparseVector(indices=[17, 2048], values=[0.3, 0.7]),
            token_count=42,
        ),
        model_version="BAAI/bge-m3@unknown|pool=cls|norm=1|dim=1024",
        dim=1024,
    )
    parsed = pb.EmbedQueryResponse.FromString(response.SerializeToString())
    assert len(parsed.embedding.dense.values) == 1024
    assert list(parsed.embedding.sparse.indices) == [17, 2048]
    assert parsed.dim == 1024
    assert parsed.model_version.endswith("|dim=1024")


def test_grpc_stubs_present() -> None:
    assert hasattr(rpc, "EmbeddingServiceServicer")
    assert hasattr(rpc, "EmbeddingServiceStub")
    assert hasattr(rpc, "add_EmbeddingServiceServicer_to_server")
