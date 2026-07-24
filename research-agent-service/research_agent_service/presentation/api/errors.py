"""Обработчики ошибок: прикладные/доменные исключения → HTTP-ответы."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from research_agent_service.application.exceptions import (
    QueryFailed,
    RateLimited,
    UnknownAgentRun,
)
from research_agent_service.domain.exceptions import DomainError
from research_agent_service.presentation.schemas.common import ErrorResponse


def _error(status: int, code: str, detail: str | None = None) -> JSONResponse:
    body = ErrorResponse(error=code, detail=detail)
    return JSONResponse(status_code=status, content=body.model_dump())


async def _rate_limited(_: Request, exc: RateLimited) -> JSONResponse:
    response = _error(429, "rate_limited")
    if exc.retry_after_s is not None:
        response.headers["Retry-After"] = str(int(exc.retry_after_s))
    return response


async def _query_failed(_: Request, exc: QueryFailed) -> JSONResponse:
    return _error(502, "query_failed", str(exc.run_id.value))


async def _unknown_run(_: Request, exc: UnknownAgentRun) -> JSONResponse:
    return _error(404, "not_found", str(exc))


async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return _error(422, "invalid_request", str(exc))


def register_error_handlers(app: FastAPI) -> None:
    """Регистрирует обработчики прикладных и доменных ошибок."""
    app.add_exception_handler(RateLimited, _rate_limited)
    app.add_exception_handler(QueryFailed, _query_failed)
    app.add_exception_handler(UnknownAgentRun, _unknown_run)
    app.add_exception_handler(DomainError, _domain_error)
