"""Traduccion de errores de dominio a respuestas HTTP.

Ningun error tecnico debe llegar al usuario tal cual. Un archivo al que le
falta una columna no es un 500: es un 422 que dice que columna falta, porque el
usuario puede arreglarlo. Un proveedor caido es un 503, porque no puede.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from agentcanvas.agent.structured import AgentFailedError
from agentcanvas.application.ports.llm import LLMError, LLMUnavailableError
from agentcanvas.domain.dataset.errors import DatasetHasNoDataError, SchemaMismatchError
from agentcanvas.domain.shared.errors import (
    DomainError,
    EmptyFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from agentcanvas.domain.visual.errors import InvalidVisualSpecError
from agentcanvas.infrastructure.web.schemas import ErrorOut

_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (SchemaMismatchError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (InvalidVisualSpecError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (AgentFailedError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (UnsupportedFileTypeError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (EmptyFileError, status.HTTP_400_BAD_REQUEST),
    (DatasetHasNoDataError, status.HTTP_409_CONFLICT),
    (LLMUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (LLMError, status.HTTP_502_BAD_GATEWAY),
)


def status_for(error: DomainError) -> int:
    for error_type, code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return code
    return status.HTTP_400_BAD_REQUEST


def problems_of(error: DomainError) -> list[str]:
    """Los detalles accionables, cuando el error los tiene."""
    if isinstance(error, AgentFailedError | InvalidVisualSpecError):
        return list(error.problems)
    if isinstance(error, SchemaMismatchError):
        compatibility = error.compatibility
        return [f"Falta la columna: {column}" for column in compatibility.missing_columns] + [
            f"La columna '{column}' deberia ser {expected} y llego como {found}"
            for column, expected, found in compatibility.type_mismatches
        ]
    return []


def as_payload(error: DomainError) -> ErrorOut:
    return ErrorOut(
        error=type(error).__name__,
        detail=str(error),
        problems=problems_of(error),
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DomainError)
        return JSONResponse(
            status_code=status_for(error),
            content=as_payload(error).model_dump(),
        )
