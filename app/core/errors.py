"""Formato comum de erro da API e handlers de exceção.

Toda resposta de erro da API sai no envelope:

    {"error": {"code": "STRING_CONSTANTE", "message": "texto", "fields": {...}}}

`fields` só aparece em erros de validação (422). Ver `.ai/adr/0001-fundacao-http-kit-api.md`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("vintex.api")


class ErrorCode:
    """Catálogo de códigos de erro compartilhados entre front e back.

    Adicione um código aqui antes de usá-lo numa rota; o front espelha esta lista.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    STORE_NOT_FOUND = "STORE_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def error_body(
    code: str, message: str, fields: dict[str, str] | None = None
) -> dict[str, Any]:
    """Monta o corpo do envelope de erro."""
    error: dict[str, Any] = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return {"error": error}


class AppError(Exception):
    """Erro de aplicação já traduzível para HTTP.

    Controllers e repositories levantam subclasses disto; a rota não precisa
    montar `HTTPException` nem decidir status.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APP_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.fields = fields

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=error_body(self.code, self.message, self.fields),
        )


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = ErrorCode.AUTH_REQUIRED


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = ErrorCode.FORBIDDEN


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.VALIDATION_ERROR


_HTTP_STATUS_CODE: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.AUTH_REQUIRED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
}


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return exc.to_response()


async def _validation_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    fields: dict[str, str] = {}
    for err in exc.errors():
        location = [str(part) for part in err["loc"] if part not in ("body", "query")]
        key = ".".join(location) or "body"
        fields[key] = err["msg"]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_body(
            ErrorCode.VALIDATION_ERROR, "Dados inválidos na requisição.", fields
        ),
    )


async def _http_exception_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _HTTP_STATUS_CODE.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else code
    return JSONResponse(
        status_code=exc.status_code, content=error_body(code, message)
    )


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro não tratado na API", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(
            ErrorCode.INTERNAL_ERROR, "Erro interno. Tente novamente mais tarde."
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Liga os handlers no app. Chamado uma vez por `create_app()`."""
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
