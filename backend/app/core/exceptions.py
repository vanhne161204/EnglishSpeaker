"""Domain exceptions and centralized exception handlers.

Using a small exception hierarchy keeps HTTP concerns out of the service layer:
services raise ``AppError`` subclasses, and the API layer maps them to responses.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for expected, handled application errors."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class BadRequestError(AppError):
    """The request is well-formed but asks for something the domain disallows.

    Used where a rule can't be expressed in the Pydantic schema — e.g. adding a
    vocabulary item to a ``questions`` section (PRD §8.2).
    """

    status_code = 400
    code = "bad_request"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ForbiddenError(AppError):
    """The caller is known but not allowed to perform this action (e.g. not the room owner)."""

    status_code = 403
    code = "forbidden"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
