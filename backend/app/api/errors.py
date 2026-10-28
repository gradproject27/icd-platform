"""One error shape for every 4xx answer: {"error": {"code", "message"}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import ApiError, ErrorCode, ErrorResponse


class ApiException(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def error_response(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ApiError(code=code, message=message))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code)


def _describe(exc: RequestValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first["loc"] if part not in ("body", "query", "path"))
    return f"{where or 'request'}: {first['msg']}"


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def _api(_: Request, exc: ApiException) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, ErrorCode.VALIDATION_ERROR, _describe(exc))
