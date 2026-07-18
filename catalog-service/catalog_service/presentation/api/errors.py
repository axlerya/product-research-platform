"""Обработчики ошибок: доменные/прикладные исключения -> RFC 9457."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from catalog_service.application.exceptions import (
    BusinessRuleViolation,
    CatalogError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from catalog_service.presentation.api.schemas.common import (
    FieldError,
    Problem,
)

_BASE = "https://errors.catalog-service"
_STATUS: dict[type[CatalogError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    BusinessRuleViolation: 400,
}


def _status_for(exc: CatalogError) -> int:
    for base, status in _STATUS.items():
        if isinstance(exc, base):
            return status
    return 400


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type="application/problem+json",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Регистрирует единые обработчики ошибок приложения."""

    @app.exception_handler(CatalogError)
    async def _catalog_error(
        request: Request, exc: CatalogError
    ) -> JSONResponse:
        status = _status_for(exc)
        problem = Problem(
            type=f"{_BASE}/{exc.code.replace('_', '-')}",
            title=exc.code.replace("_", " ").title(),
            status=status,
            code=exc.code,
            detail=exc.message,
            instance=request.url.path,
            meta=exc.meta or None,
        )
        return _problem_response(problem)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            FieldError(
                loc=[str(part) for part in err["loc"]],
                msg=err["msg"],
                type=err["type"],
            )
            for err in exc.errors()
        ]
        problem = Problem(
            type=f"{_BASE}/validation-error",
            title="Validation Error",
            status=422,
            code="validation_error",
            instance=request.url.path,
            errors=errors,
        )
        return _problem_response(problem)
