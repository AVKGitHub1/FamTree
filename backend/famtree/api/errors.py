"""Uniform JSON error responses: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from famtree.domain.errors import DomainError


class RateLimited(DomainError):
    status = 429
    code = "rate_limited"

    def __init__(self, retry_after: float) -> None:
        super().__init__(
            "Too many sign-in attempts. Wait a few minutes and try again.",
            retry_after=int(retry_after),
        )
        self.retry_after = int(retry_after)


def _body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
        return JSONResponse(
            _body(exc.code, exc.message, exc.details), status_code=exc.status, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        message = first.get("msg", "Invalid request.")
        # Echo only the location and message, never the submitted value.
        return JSONResponse(
            _body("invalid_input", f"{where}: {message}" if where else message),
            status_code=422,
        )
