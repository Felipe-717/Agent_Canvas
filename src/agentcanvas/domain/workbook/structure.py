"""Como se extrae una tabla de un archivo que no es una tabla.

Los Excel reales no empiezan en A1 con cabeceras limpias. Traen titulos
combinados, parrafos de instrucciones, filas de ejemplo, totales al pie, hojas
auxiliares vacias y a veces varias tablas en la misma hoja, una al lado de otra.

`TableSpec` es la respuesta a "donde esta la tabla de verdad". Se guarda igual
que una `VisualSpec`: el mes que viene, el mismo archivo raro se lee sin volver
a preguntarle nada a nadie.
"""

from __future__ import annotations

import re
from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, model_validator

CSV_SHEET = "datos"
"""Nombre de hoja unico que se le da a un CSV.

Asi el resto del sistema no tiene que distinguir entre CSV y Excel: un CSV
es un libro de una sola hoja."""


class TableSpec(BaseModel):
    """Coordenadas de una tabla dentro de un libro. Todo en base 1, como Excel.

    Se usa base 1 a proposito: el usuario y el modelo hablan de "la fila 11"
    mirando Excel, y traducir a base 0 solo introduce errores.
    """

    model_config = ConfigDict(frozen=True)

    sheet: str
    header_row: int = Field(ge=1)
    """Fila donde estan los nombres de columna."""

    first_data_row: int | None = Field(default=None, ge=1)
    """Por defecto, la siguiente a la cabecera."""

    last_data_row: int | None = Field(default=None, ge=1)
    """Para cortar antes de una fila de totales."""

    first_column: int = Field(default=1, ge=1)
    last_column: int | None = Field(default=None, ge=1)
    """Delimitar columnas es lo que permite leer una de varias tablas puestas
    lado a lado en la misma hoja."""

    skip_rows: tuple[int, ...] = ()
    """Filas sueltas a descartar, como la de ejemplo que algunas plantillas
    dejan justo debajo de la cabecera."""

    drop_empty_columns: bool = True
    drop_empty_rows: bool = True

    @model_validator(mode="after")
    def _check_ranges(self) -> TableSpec:
        if self.data_start <= self.header_row:
            raise ValueError("Los datos deben empezar despues de la fila de cabecera")
        if self.last_data_row is not None and self.last_data_row < self.data_start:
            raise ValueError("El rango de datos esta invertido")
        if self.last_column is not None and self.last_column < self.first_column:
            raise ValueError("El rango de columnas esta invertido")
        return self

    @property
    def data_start(self) -> int:
        return self.first_data_row or self.header_row + 1

    def describe(self) -> str:
        """Como se lo contamos al usuario."""
        columns = (
            f"columnas {self.first_column}-{self.last_column}"
            if self.last_column
            else f"desde la columna {self.first_column}"
        )
        rows = f"filas {self.data_start}-{self.last_data_row}" if self.last_data_row else (
            f"desde la fila {self.data_start}"
        )
        return f"hoja '{self.sheet}', cabecera en la fila {self.header_row}, {rows}, {columns}"


class SheetOverview(BaseModel):
    """Lo que se sabe de una hoja sin haberla leido entera."""

    model_config = ConfigDict(frozen=True)

    name: str
    rows: int
    columns: int
    filled_cells: int
    is_empty: bool = False

    @property
    def density(self) -> float:
        """Proporcion de celdas con contenido.

        Una hoja densa suele ser una tabla; una muy dispersa suele ser notas,
        un formulario o restos. Es una pista, no una certeza.
        """
        total = self.rows * self.columns
        return self.filled_cells / total if total else 0.0


class WorkbookOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    sheets: tuple[SheetOverview, ...]

    @property
    def sheet_names(self) -> tuple[str, ...]:
        return tuple(sheet.name for sheet in self.sheets)

    def get(self, name: str) -> SheetOverview | None:
        return next((sheet for sheet in self.sheets if sheet.name == name), None)

    @property
    def candidates(self) -> tuple[SheetOverview, ...]:
        """Hojas que podrian contener una tabla, de mas a menos prometedora.

        Ordena por celdas con contenido y descarta las vacias, para que el
        agente no gaste iteraciones mirando `Hoja3`.
        """
        useful = [sheet for sheet in self.sheets if not sheet.is_empty and sheet.filled_cells > 0]
        return tuple(sorted(useful, key=lambda sheet: sheet.filled_cells, reverse=True))


class CellWindow(BaseModel):
    """Un trozo rectangular de celdas, tal cual estan en el archivo."""

    model_config = ConfigDict(frozen=True)

    sheet: str
    first_row: int
    first_column: int
    rows: tuple[tuple[str, ...], ...]

    def render(self, max_width: int = 28) -> str:
        """Vista con numeros de fila, que es lo que se le ensena al modelo.

        Los numeros importan: sin ellos el modelo no puede decir "la cabecera
        esta en la fila 11", que es justo lo que se le pide.
        """
        lines: list[str] = []
        for offset, row in enumerate(self.rows):
            number = self.first_row + offset
            cells = [cell[:max_width] if cell else "·" for cell in row]
            lines.append(f"{number:>4} | " + " | ".join(cells))
        return "\n".join(lines)


def parallel_tables_hint(rows: tuple[tuple[str, ...], ...]) -> str | None:
    """Avisa si alguna fila parece la cabecera de varias tablas en paralelo.

    Es una pista, no una decision: se da al listar las hojas para que el agente
    no empiece con el pie cambiado, pero sigue eligiendo el las coordenadas.
    """
    for row in rows:
        celdas = [cell.strip().lower() for cell in row if cell.strip()]
        if len(celdas) < 4:
            continue
        repetido = repeated_group(celdas)
        if repetido is not None:
            grupo, veces = repetido
            return (
                f"ojo: parece contener {veces} tablas en paralelo "
                f"(se repite {', '.join(grupo)})"
            )
    return None


def repeated_group(names: list[str]) -> tuple[tuple[str, ...], int] | None:
    """Nombres de columna que se repiten, si delatan tablas puestas en paralelo.

    No se busca periodicidad exacta. Las cabeceras reales tienen variaciones -en
    una hoja con nueve camas de germinacion, una ponia `chapola` donde las demas
    ponen `semilla`- y exigir un patron perfecto hacia que no saltara el aviso
    justo en el caso que mas importaba.
    """
    bases = [re.sub(r"_\d+$", "", name) for name in names]
    counts = Counter(bases)
    repeated = {name: n for name, n in counts.items() if n > 1}
    if not repeated:
        return None

    veces = max(repeated.values())
    # Dos columnas con el mismo nombre son una cabecera duplicada. Que se repita
    # un grupo entero, o que una sola se repita tres veces, ya es otra cosa.
    if veces < 3 and len(repeated) < 2:
        return None
    grupo = tuple(dict.fromkeys(name for name in bases if name in repeated))
    return grupo, veces
