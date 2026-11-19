from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse

from app.api.deps import get_logger
from app.domain.exceptions import AgentError, DomainError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request


def _log_failure(event: str, exc: Exception) -> None:
    cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
    get_logger().error(event, error=type(exc).__name__, cause=cause)


async def _agent_error(_: Request, exc: Exception) -> JSONResponse:
    _log_failure("agent.failed", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Agent failed to produce a reply"},
    )


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    _log_failure("domain.failed", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal error"}
    )


def install_error_handlers(app: FastAPI) -> None:
    """Map domain errors to HTTP. Logs the error type and cause type, never any content."""
    app.add_exception_handler(AgentError, _agent_error)
    app.add_exception_handler(DomainError, _domain_error)
