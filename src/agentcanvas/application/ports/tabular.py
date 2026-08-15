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

    warnings: tuple[str, ...] = ()
    """Lo que huele raro en lo extraido.

    Una extraccion puede salir sin errores y aun asi estar mal: nueve tablas
    puestas lado a lado se leen como una sola de veintisiete columnas, y una
    fila de totales entra como si fuera un dato. Callarselo produce graficos
    que parecen correctos, que es el peor fallo posible. Estos avisos viajan
    hasta el modelo para que pregunte o rectifique."""

