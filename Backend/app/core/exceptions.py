from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# ── Domain exception hierarchy ────────────────────────────────────────────────

class HadhaException(Exception):
    """Base for all application exceptions."""

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(HadhaException):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(HadhaException):
    status_code = status.HTTP_409_CONFLICT


class ValidationError(HadhaException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class AuthenticationError(HadhaException):
    status_code = status.HTTP_401_UNAUTHORIZED


class AuthorizationError(HadhaException):
    status_code = status.HTTP_403_FORBIDDEN


class RateLimitError(HadhaException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class ServiceUnavailableError(HadhaException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class PaymentError(HadhaException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED


class InventoryError(HadhaException):
    """Raised when stock is insufficient for an operation."""
    status_code = status.HTTP_409_CONFLICT


class WebhookVerificationError(HadhaException):
    status_code = status.HTTP_400_BAD_REQUEST


# ── Response helpers ──────────────────────────────────────────────────────────

def _error_response(
    status_code: int,
    message: str,
    code: str | None = None,
    detail: object = None,
) -> JSONResponse:
    resolved_code = code or "ERROR"
    body: dict = {
        "success": False,
        "code": resolved_code,
        "message": message,
        "error": message,
        "data": detail,
    }
    return JSONResponse(status_code=status_code, content=body)


# ── Global exception handlers ─────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HadhaException)
    async def hadha_exception_handler(
        request: Request, exc: HadhaException
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,  # type: ignore[attr-defined]
            message=exc.message,
            code=exc.code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            errors.append({"field": field, "message": error["msg"]})
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Validation failed",
            code="VALIDATION_ERROR",
            detail=errors,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            message="The requested resource was not found",
            code="NOT_FOUND",
        )

    @app.exception_handler(405)
    async def method_not_allowed_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            message="Method not allowed",
            code="METHOD_NOT_ALLOWED",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        import structlog
        log = structlog.get_logger()
        # exc_info=True captures the full traceback so it appears in both the
        # dev ConsoleRenderer (inline) and the prod JSONRenderer (structured).
        # request_id is already in structlog contextvars from RequestIDMiddleware.
        log.error(
            "unhandled_exception",
            exc_info=True,
            exc_type=type(exc).__name__,
            path=request.url.path,
            method=request.method,
        )
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="An internal error occurred",
            code="INTERNAL_ERROR",
        )
