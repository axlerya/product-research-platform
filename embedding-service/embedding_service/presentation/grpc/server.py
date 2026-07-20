"""Сборка grpc.aio-сервера (§6.9). Runtime-обвязка (вне coverage)."""

from collections.abc import Sequence

import grpc
from grpc_health.v1 import health, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2 as pb,
)
from embedding_service.infrastructure.grpc._generated import (
    embedding_pb2_grpc as rpc,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2 as reranker_pb,
)
from embedding_service.infrastructure.grpc._generated import (
    reranker_pb2_grpc as reranker_rpc,
)
from embedding_service.presentation.grpc.reranker_servicer import (
    RerankerServicer,
)
from embedding_service.presentation.grpc.servicer import EmbeddingServicer


def build_server(
    servicer: EmbeddingServicer,
    health_servicer: health.aio.HealthServicer,
    *,
    reranker_servicer: RerankerServicer | None = None,
    address: str,
    interceptors: Sequence[grpc.aio.ServerInterceptor] | None = None,
    max_concurrent_rpcs: int | None = None,
    reflection_enabled: bool = False,
) -> tuple[grpc.aio.Server, int]:
    """Собирает сервер, привязывает порт и возвращает (server, bound_port).

    ``reranker_servicer`` регистрируется дополнительно и только когда reranker
    включён (``RERANKER_ENABLED``); иначе RerankerService отсутствует и вызов
    Rerank возвращает UNIMPLEMENTED. EmbeddingService-часть не меняется.
    """
    server = grpc.aio.server(
        interceptors=list(interceptors or ()),
        maximum_concurrent_rpcs=max_concurrent_rpcs,
    )
    rpc.add_EmbeddingServiceServicer_to_server(servicer, server)
    if reranker_servicer is not None:
        reranker_rpc.add_RerankerServiceServicer_to_server(
            reranker_servicer, server
        )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    if reflection_enabled:
        service_names = [
            pb.DESCRIPTOR.services_by_name["EmbeddingService"].full_name,
            reflection.SERVICE_NAME,
        ]
        if reranker_servicer is not None:
            service_names.append(
                reranker_pb.DESCRIPTOR.services_by_name[
                    "RerankerService"
                ].full_name
            )
        reflection.enable_server_reflection(tuple(service_names), server)
    bound_port = server.add_insecure_port(address)
    return server, bound_port
