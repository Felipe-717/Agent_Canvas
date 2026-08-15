"""Lectura de CSV/XLSX con pandas e inferencia de tipos logicos.

Aqui vive toda la fealdad de los archivos reales: encodings raros, separadores
que no son comas, cabeceras con acentos y espacios, columnas fantasma que Excel
anade al final, fechas escritas de seis maneras. El resto del sistema solo ve un
`DatasetSchema` limpio y un Parquet.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api import types as pdt

from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.domain.dataset.schema import (
    ColumnSchema,
    ColumnType,
    DatasetSchema,
    normalize_column_name,
)

# Encodings por orden de probabilidad en Excel exportado desde Windows en es-ES.
_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

_DATE_LIKE = re.compile(
    r"^\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})([ T]\d{1,2}:\d{2}.*)?\s*$"
)

# Proporcion de la muestra que debe parsear como fecha para convertir la columna.
_DATE_THRESHOLD = 0.9
_SAMPLE_SIZE = 200


class PandasTabularReader:
    """Implementa `TabularReaderPort`."""

    def read(
        self,
        source: Path,
        *,
        destination: Path,
        preview_rows: int = 10,
    ) -> NormalizedTable:
        frame = _load(source)
        frame = _drop_ghost_columns(frame)
        frame = _rename_to_normalized(frame)
        frame = _coerce_dates(frame)

        destination.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(destination, index=False)

        columns = tuple(
            ColumnSchema(
                name=str(name),
                original_name=str(original),
                type=_logical_type(frame[name]),
                nullable=bool(frame[name].isna().any()),
            )
            for name, original in zip(frame.columns, frame.attrs["original_names"], strict=True)
        )
        return NormalizedTable(
            schema_=DatasetSchema(columns=columns),
            row_count=len(frame),
            preview=_preview(frame, preview_rows),
        )


def _load(source: Path) -> pd.DataFrame:
    if source.suffix.lower() == ".xlsx":
        return pd.read_excel(source, engine="openpyxl")
    return _load_csv(source)


def _load_csv(source: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in _CSV_ENCODINGS:
        try:
            # sep=None + engine="python" detecta si el separador es , ; o tab,
            # que es la primera causa de "el CSV se lee en una sola columna".
            return pd.read_csv(source, sep=None, engine="python", encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            last_error = error
    raise ValueError(f"No se pudo leer el CSV '{source.name}': {last_error}")


def _drop_ghost_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Elimina las columnas sin nombre y completamente vacias que deja Excel."""
    ghosts = [
        column
        for column in frame.columns
        if str(column).startswith("Unnamed:") and frame[column].isna().all()
    ]
    return frame.drop(columns=ghosts) if ghosts else frame


def _rename_to_normalized(frame: pd.DataFrame) -> pd.DataFrame:
    """Renombra a nombres normalizados y guarda los originales en `attrs`.

    Dos cabeceras distintas pueden normalizar al mismo nombre ("Valor" y
    "valor "); en ese caso se desambigua con sufijo en vez de perder una.
    """
    originals = [str(column) for column in frame.columns]
    seen: Counter[str] = Counter()
    normalized: list[str] = []
    for original in originals:
        candidate = normalize_column_name(original) or "columna"
        seen[candidate] += 1
        if seen[candidate] > 1:
            candidate = f"{candidate}_{seen[candidate]}"
        normalized.append(candidate)

    renamed = frame.copy()
    renamed.columns = pd.Index(normalized)
    renamed.attrs["original_names"] = originals
    return renamed


def _coerce_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Convierte a datetime las columnas de texto que claramente son fechas.

    Solo actua cuando casi toda la muestra tiene forma de fecha: convertir a la
    ligera es peor que no convertir, porque un codigo de producto como
    "12-3456" se destruiria.
    """
    for column in frame.columns:
        series = frame[column]
        if not pdt.is_object_dtype(series):
            continue
        sample = series.dropna().head(_SAMPLE_SIZE)
        if sample.empty:
            continue
        looks_like_date = sample.astype(str).str.match(_DATE_LIKE).mean()
        if looks_like_date < _DATE_THRESHOLD:
            continue
        converted = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)
        # Si la conversion perdio datos que no eran nulos, se descarta.
        if converted.notna().sum() >= series.notna().sum() * _DATE_THRESHOLD:
            frame[column] = converted
    return frame


def _logical_type(series: pd.Series[Any]) -> ColumnType:
    if pdt.is_bool_dtype(series):
        return ColumnType.BOOLEAN
    if pdt.is_integer_dtype(series):
        return ColumnType.INTEGER
    if pdt.is_float_dtype(series):
        return ColumnType.FLOAT
    if pdt.is_datetime64_any_dtype(series):
        values = series.dropna()
        # Sin componente horaria en ninguna fila, es una fecha, no un instante.
        if not values.empty and bool((values.dt.normalize() == values).all()):
            return ColumnType.DATE
        return ColumnType.DATETIME
    if pdt.is_object_dtype(series) or pdt.is_string_dtype(series):
        return ColumnType.STRING
    return ColumnType.UNKNOWN


def _preview(frame: pd.DataFrame, rows: int) -> tuple[dict[str, object], ...]:
    head = frame.head(rows)
    # `mode="json"`-ish: fechas y NaN deben salir serializables para el LLM y la API.
    records = head.astype(object).where(pd.notna(head), None).to_dict(orient="records")
    return tuple(
        {str(key): _jsonable(value) for key, value in record.items()} for record in records
    )


def _jsonable(value: Any) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
