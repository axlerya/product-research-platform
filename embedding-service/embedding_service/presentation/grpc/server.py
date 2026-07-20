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
from embedding_service.presentation.grpc.servicer import EmbeddingServicer


def build_server(
    servicer: EmbeddingServicer,
    health_servicer: health.aio.HealthServicer,
    *,
    address: str,
    interceptors: Sequence[grpc.aio.ServerInterceptor] | None = None,
    max_concurrent_rpcs: int | None = None,
    reflection_enabled: bool = False,
) -> tuple[grpc.aio.Server, int]:
    """Собирает сервер, привязывает порт и возвращает (server, bound_port)."""
    server = grpc.aio.server(
        interceptors=list(interceptors or ()),
        maximum_concurrent_rpcs=max_concurrent_rpcs,
    )
    rpc.add_EmbeddingServiceServicer_to_server(servicer, server)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    if reflection_enabled:
        service_names = (
            pb.DESCRIPTOR.services_by_name["EmbeddingService"].full_name,
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(service_names, server)
    bound_port = server.add_insecure_port(address)
    return server, bound_port
