"""Маппинг прикладных исключений в gRPC status codes (§6.6)."""

import grpc

from embedding_service.application.exceptions import (
    ApplicationError,
    InferenceError,
    InferenceOverloadedError,
    InferenceTimeoutError,
    ModelNotReadyError,
    ProbeFailed,
    ValidationError,
)

_STATUS: dict[type[ApplicationError], grpc.StatusCode] = {
    ValidationError: grpc.StatusCode.INVALID_ARGUMENT,
    ProbeFailed: grpc.StatusCode.FAILED_PRECONDITION,
    InferenceOverloadedError: grpc.StatusCode.RESOURCE_EXHAUSTED,
    InferenceTimeoutError: grpc.StatusCode.DEADLINE_EXCEEDED,
    ModelNotReadyError: grpc.StatusCode.UNAVAILABLE,
    InferenceError: grpc.StatusCode.INTERNAL,
}


def to_status_code(exc: Exception) -> grpc.StatusCode:
    """Прикладное исключение → gRPC status (всё прочее → INTERNAL)."""
    for exc_type, code in _STATUS.items():
        if isinstance(exc, exc_type):
            return code
    return grpc.StatusCode.INTERNAL
