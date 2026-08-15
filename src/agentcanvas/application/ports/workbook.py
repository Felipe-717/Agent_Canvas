from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.domain.workbook.structure import CellWindow, TableSpec, WorkbookOverview


class WorkbookReaderPort(Protocol):
    """Lectura exploratoria de un libro, antes de saber donde esta la tabla.

    Existe porque `TabularReaderPort` asume lo que en los archivos reales casi
    nunca se cumple: que la primera fila son las cabeceras y que hay una sola
    tabla. Este puerto no asume nada; devuelve celdas crudas para que alguien
    -el agente- decida.
    """

    def overview(self, source: Path) -> WorkbookOverview: ...

    def peek(
        self,
        source: Path,
        *,
        sheet: str,
        first_row: int = 1,
        rows: int = 15,
        first_column: int = 1,
        columns: int = 12,
    ) -> CellWindow: ...

    def extract(self, source: Path, spec: TableSpec, *, destination: Path) -> NormalizedTable:
        """Aplica la spec y deja la tabla normalizada en Parquet."""
        ...
