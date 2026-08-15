from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentcanvas.domain.dataset.schema import ColumnType


class ResultColumn(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    type: ColumnType


class VisualData(BaseModel):
    """Resultado de ejecutar una `VisualSpec`.

    Formato largo: cuando hay `group_by`, cada fila lleva su categoria en una
    columna en vez de haber una columna por serie. Pivotar es trabajo del
    frontend, que es quien sabe como quiere alimentar a ECharts; asi el motor
    devuelve siempre la misma forma.

    Los valores son JSON-serializables: fechas en ISO y nulos como `None`.
    """

    model_config = ConfigDict(frozen=True)

    columns: tuple[ResultColumn, ...]
    rows: tuple[dict[str, object], ...]
    truncated: bool = False
    """True si `limit` recorto filas que existian."""
