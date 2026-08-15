from __future__ import annotations

from pathlib import Path
from typing import Protocol

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


class TabularReaderPort(Protocol):
    """Lee CSV/XLSX, infiere tipos y escribe la version normalizada en Parquet.

    Toda la fealdad de los archivos reales (encodings, separadores, cabeceras
    con espacios, columnas fantasma) queda encerrada detras de este puerto.
    """

    def read(
        self,
        source: Path,
        *,
        destination: Path,
        preview_rows: int = 10,
    ) -> NormalizedTable: ...
