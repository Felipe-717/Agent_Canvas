from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agentcanvas.domain.dataset.schema import DatasetSchema
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec


class QueryEnginePort(Protocol):
    """Ejecuta una `VisualSpec` sobre un dataset normalizado.

    Deliberadamente sincrono y sin estado: es una funcion pura de (spec, datos)
    a resultado. Esa es la propiedad que permite recalcular un dashboard entero
    sin llamar al LLM, y la que hace que el mismo archivo produzca siempre los
    mismos numeros.
    """

    def execute(self, spec: VisualSpec, *, source: Path, schema: DatasetSchema) -> VisualData: ...

