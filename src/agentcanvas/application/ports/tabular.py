from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentcanvas.domain.dataset.schema import DatasetSchema


class NormalizedTable(BaseModel):
    """Resultado de leer un archivo y dejarlo en forma canonica."""

    model_config = ConfigDict(frozen=True)

    schema_: DatasetSchema
    row_count: int
    preview: tuple[dict[str, object], ...] = ()
    """Primeras filas. Es lo que se le ensena al agente para que entienda los
    datos sin tener que darle el archivo entero."""

