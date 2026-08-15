"""DTOs de la API.

Separados de las entidades de dominio a proposito: la forma del JSON que
consume el frontend es un contrato publico que evoluciona a otro ritmo que el
modelo interno. `VisualSpec` y `VisualData` si viajan tal cual, porque *son* el
contrato con el frontend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.agent.trace import AgentTrace, StepKind
from agentcanvas.application.ports.llm import Usage
from agentcanvas.domain.dataset.entities import Dataset, DatasetVersion
from agentcanvas.domain.dataset.schema import ColumnSchema
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec


class ColumnOut(BaseModel):
    name: str
    original_name: str
    type: str
    nullable: bool

    @classmethod
    def of(cls, column: ColumnSchema) -> ColumnOut:
        return cls(
            name=column.name,
            original_name=column.original_name,
            type=str(column.type),
            nullable=column.nullable,
        )


class DatasetOut(BaseModel):
    id: str
    name: str
    row_count: int
    fingerprint: str
    columns: list[ColumnOut]
    current_version_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, dataset: Dataset) -> DatasetOut:
        return cls(
            id=dataset.id,
            name=dataset.name,
            row_count=dataset.row_count,
            fingerprint=dataset.fingerprint,
            columns=[ColumnOut.of(column) for column in dataset.schema_.columns],
            current_version_id=dataset.current_version_id,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )


class VersionOut(BaseModel):
    id: str
    row_count: int
    created_at: datetime

    @classmethod
    def of(cls, version: DatasetVersion) -> VersionOut:
        return cls(id=version.id, row_count=version.row_count, created_at=version.created_at)


class IngestOut(BaseModel):
    dataset: DatasetOut
    version: VersionOut
    created_dataset: bool
    """False significa que el archivo se anadio a un dataset existente, y por
    tanto que los graficos guardados sobre el ya reflejan los datos nuevos."""

    preview: list[dict[str, object]]


class CreateVisualIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class RenderVisualIn(BaseModel):
    spec: VisualSpec
    """La spec guardada. Ejecutarla no pasa por el modelo."""


class TraceOut(BaseModel):
    attempts: int
    repairs: int
    usage: Usage
    problems: list[str]
    """Lo que se le reprocho al modelo por el camino. Vacio si acerto a la
    primera. Se expone porque un agente que se corrige en silencio es un agente
    que nadie puede mejorar."""

    @classmethod
    def of(cls, trace: AgentTrace) -> TraceOut:
        return cls(
            attempts=trace.repairs + 1,
            repairs=trace.repairs,
            usage=trace.usage,
            problems=[
                problem
                for step in trace.steps
                if step.kind is StepKind.REJECTED
                for problem in step.problems
            ],
        )


class VisualOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    spec: VisualSpec
    data: VisualData
    trace: TraceOut | None = None


class ErrorOut(BaseModel):
    error: str
    detail: str
    problems: list[str] = []
