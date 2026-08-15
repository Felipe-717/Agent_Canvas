"""Normalizacion de una tabla ya extraida.

Aqui vive la fealdad de los archivos reales: cabeceras con acentos y espacios,
columnas fantasma que Excel anade al final, fechas escritas de seis maneras. El
resto del sistema solo ve nombres de columna limpios y tipos logicos.

Lo usa el lector de libros despues de recortar la tabla de donde estuviera.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd
from pandas.api import types as pdt

from agentcanvas.domain.dataset.schema import (
    ColumnType,
    normalize_column_name,
)

_TIME_PART = r"([ T]\d{1,2}:\d{2}.*)?"
_ISO_DATE = re.compile(rf"^\s*\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}{_TIME_PART}\s*$")
"""Ano primero. Con estas no se puede aplicar `dayfirst`: "2026-03-05" es el 5
de marzo, y leerla al reves la convierte en el 3 de mayo sin avisar de nada."""

_LOCAL_DATE = re.compile(rf"^\s*\d{{1,2}}[-/]\d{{1,2}}[-/]\d{{2,4}}{_TIME_PART}\s*$")
"""Dia primero, que es como se escriben las fechas en espanol."""

_DATE_LIKE = re.compile(rf"({_ISO_DATE.pattern})|({_LOCAL_DATE.pattern})")

# Proporcion de la muestra que debe parsear como fecha para convertir la columna.
_DATE_THRESHOLD = 0.9
_SAMPLE_SIZE = 200
_NUMERIC_THRESHOLD = 0.95


def finalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Deja un DataFrame en forma canonica: nombres limpios y tipos reales.

    El orden importa. Los numeros van antes que las fechas porque una fecha
    completa no parsea como numero, pero un ano suelto si; al reves, "2026"
    acabaria convertido en el 1 de enero.
    """
    renamed = _rename_to_normalized(_drop_ghost_columns(frame))
    return _coerce_dates(_coerce_numbers(renamed))


def _is_text(series: pd.Series[Any]) -> bool:
    """True si la columna trae texto sin interpretar.

    No basta con `is_object_dtype`: hasta pandas 2 una columna de texto llegaba
    como `object`, y desde pandas 3 llega como `str`. Mirando solo `object`, en
    pandas 3 no se convertia ni un numero ni una fecha, el schema salia entero
    de tipo texto y cualquier suma se rechazaba como invalida. Se comprueban los
    dos, que es cierto en las dos versiones.
    """
    if isinstance(series.dtype, pd.CategoricalDtype):
        # `is_string_dtype` dice que si a una categorica de textos, y convertirla
        # aqui destruiria justamente lo que la hace categorica.
        return False
    return bool(pdt.is_object_dtype(series) or pdt.is_string_dtype(series))


def _coerce_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    """Convierte a numero las columnas de texto que lo son.

    Hace falta porque de un CSV todo llega como texto: sin esto, sumar una
    columna de importes seria imposible y el agente veria "texto" donde hay
    dinero.
    """
    for column in frame.columns:
        series = frame[column]
        if not _is_text(series):
            continue
        present = series.dropna()
        if present.empty:
            continue
        converted = pd.to_numeric(series, errors="coerce")
        # Se exige casi unanimidad: una columna con un "N/A" suelto sigue
        # siendo numerica, pero una de codigos con algun numero no lo es.
        if converted.notna().sum() >= len(present) * _NUMERIC_THRESHOLD:
            frame[column] = converted
    return frame


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
        if not _is_text(series):
            continue
        sample = series.dropna().head(_SAMPLE_SIZE)
        if sample.empty:
            continue
        texto = sample.astype(str)
        if texto.str.match(_DATE_LIKE).mean() < _DATE_THRESHOLD:
            continue
        # `dayfirst` solo donde tiene sentido. Aplicarlo a una columna ISO
        # intercambia dia y mes en silencio: "2026-03-05" se guardaba como el 3
        # de mayo, y a partir de ahi todo lo demas cuadraba y era falso.
        if texto.str.match(_ISO_DATE).mean() >= _DATE_THRESHOLD:
            converted = pd.to_datetime(series, errors="coerce", format="ISO8601")
        else:
            converted = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=True)
        # Si la conversion perdio datos que no eran nulos, se descarta.
        if converted.notna().sum() >= series.notna().sum() * _DATE_THRESHOLD:
            frame[column] = converted
    return frame


def logical_type(series: pd.Series[Any]) -> ColumnType:
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


def preview_rows_of(frame: pd.DataFrame, rows: int) -> tuple[dict[str, object], ...]:
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

