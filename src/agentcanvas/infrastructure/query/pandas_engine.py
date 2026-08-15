"""Compilador de `VisualSpec` a operaciones de pandas.

Sin LLM en ningun punto: misma spec y mismos datos dan siempre el mismo
resultado. Es lo que permite que subir el Excel del mes siguiente recalcule
veinte graficos guardados sin gastar un token ni arriesgar una alucinacion.

El dia que los volumenes lo pidan, este adaptador se sustituye por uno de DuckDB
sobre el mismo Parquet sin tocar nada mas: el puerto es el mismo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from agentcanvas.domain.dataset.schema import DatasetSchema
from agentcanvas.domain.visual.result import ResultColumn, VisualData
from agentcanvas.domain.visual.spec import (
    Aggregation,
    Dimension,
    Filter,
    FilterOperator,
    Measure,
    SortDirection,
    TimeGrain,
    VisualSpec,
)
from agentcanvas.domain.visual.validation import ensure_valid, result_keys, result_type

# Columna sintetica para contar filas sin depender de ninguna columna real.
_ROW_MARKER = "__row__"

_AGGREGATION_FUNCTIONS: dict[Aggregation, str] = {
    Aggregation.SUM: "sum",
    Aggregation.AVG: "mean",
    Aggregation.MIN: "min",
    Aggregation.MAX: "max",
    Aggregation.COUNT: "count",
    Aggregation.COUNT_DISTINCT: "nunique",
    Aggregation.MEDIAN: "median",
}

# Alias de *periodo* (D/W/M/Q/Y), no de offset: `to_period` no acepta "MS".
_GRAIN_FREQUENCIES: dict[TimeGrain, str] = {
    TimeGrain.DAY: "D",
    TimeGrain.WEEK: "W",
    TimeGrain.MONTH: "M",
    TimeGrain.QUARTER: "Q",
    TimeGrain.YEAR: "Y",
}


class PandasQueryEngine:
    """Implementa `QueryEnginePort`."""

    def execute(self, spec: VisualSpec, *, source: Path, schema: DatasetSchema) -> VisualData:
        # Validar antes de leer: si la spec esta mal, el error debe ser sobre la
        # spec, no un KeyError de pandas a mitad de un groupby.
        ensure_valid(spec, schema)

        frame = _load(source, spec)
        frame = _apply_filters(frame, spec.filters, schema)
        frame = _apply_time_grains(frame, spec.dimensions)

        result = _select_raw(frame, spec) if spec.is_raw else _aggregate(frame, spec)
        result = _apply_sort(result, spec)
        result, truncated = _apply_limit(result, spec)

        return VisualData(
            columns=tuple(
                ResultColumn(
                    key=key,
                    label=_label_for(spec, key),
                    type=result_type(spec, key, schema),
                )
                for key in result_keys(spec)
            ),
            rows=_to_rows(result, result_keys(spec)),
            truncated=truncated,
        )


def _load(source: Path, spec: VisualSpec) -> pd.DataFrame:
    # Solo las columnas que la spec necesita: en Parquet esto es proyeccion
    # real, no un descarte posterior.
    needed = list(spec.referenced_fields)
    frame = pd.read_parquet(source, columns=needed) if needed else pd.read_parquet(source)
    frame[_ROW_MARKER] = 1
    return frame


def _apply_filters(
    frame: pd.DataFrame, filters: tuple[Filter, ...], schema: DatasetSchema
) -> pd.DataFrame:
    for filter in filters:
        frame = frame[_mask_for(frame, filter, schema)]
    return frame


def _mask_for(frame: pd.DataFrame, filter: Filter, schema: DatasetSchema) -> pd.Series[bool]:
    series = frame[filter.field]
    operator = filter.operator

    if operator is FilterOperator.IS_NULL:
        return series.isna()
    if operator is FilterOperator.NOT_NULL:
        return series.notna()
    if operator is FilterOperator.CONTAINS:
        return series.astype(str).str.contains(str(filter.value), case=False, na=False)

    column = schema.get(filter.field)
    temporal = column is not None and column.type.is_temporal

    if operator is FilterOperator.IN:
        return series.isin([_coerce(v, temporal) for v in filter.values])
    if operator is FilterOperator.NOT_IN:
        return ~series.isin([_coerce(v, temporal) for v in filter.values])
    if operator is FilterOperator.BETWEEN:
        low, high = (_coerce(v, temporal) for v in filter.values)
        return series.between(low, high)

    value = _coerce(filter.value, temporal)
    comparisons = {
        FilterOperator.EQ: series.eq,
        FilterOperator.NE: series.ne,
        FilterOperator.GT: series.gt,
        FilterOperator.GTE: series.ge,
        FilterOperator.LT: series.lt,
        FilterOperator.LTE: series.le,
    }
    return comparisons[operator](value)


def _coerce(value: Any, temporal: bool) -> Any:
    """Las fechas llegan como texto ISO desde el JSON de la spec."""
    if temporal and isinstance(value, str):
        return pd.Timestamp(value)
    return value


def _apply_time_grains(frame: pd.DataFrame, dimensions: tuple[Dimension, ...]) -> pd.DataFrame:
    for dimension in dimensions:
        if dimension.time_grain is None:
            continue
        frequency = _GRAIN_FREQUENCIES[dimension.time_grain]
        # `to_period().to_timestamp()` deja el inicio del periodo, que es lo que
        # un eje temporal necesita para ordenarse solo.
        frame[dimension.key] = (
            pd.to_datetime(frame[dimension.field]).dt.to_period(frequency).dt.to_timestamp()
        )
    return frame


def _aggregate(frame: pd.DataFrame, spec: VisualSpec) -> pd.DataFrame:
    aggregations = {measure.key: _aggregation_for(measure) for measure in spec.y}
    group_keys = [dimension.key for dimension in spec.dimensions]

    if not group_keys:
        # KPI: una sola fila con los totales.
        row = {
            key: _apply_aggregation(frame, column, function)
            for key, (column, function) in aggregations.items()
        }
        return pd.DataFrame([row])

    grouped = frame.groupby(group_keys, dropna=False, observed=True)
    result = grouped.agg(**{key: pd.NamedAgg(*value) for key, value in aggregations.items()})
    return result.reset_index()


def _aggregation_for(measure: Measure) -> tuple[str, str]:
    if measure.field is None:
        # `count` sin columna cuenta filas, incluidas las que tienen nulos.
        return (_ROW_MARKER, "sum")
    return (measure.field, _AGGREGATION_FUNCTIONS[measure.aggregation])


def _apply_aggregation(frame: pd.DataFrame, column: str, function: str) -> Any:
    return getattr(frame[column], function)()


def _select_raw(frame: pd.DataFrame, spec: VisualSpec) -> pd.DataFrame:
    return frame[list(result_keys(spec))].copy()


def _apply_sort(frame: pd.DataFrame, spec: VisualSpec) -> pd.DataFrame:
    if spec.sort is not None:
        return frame.sort_values(
            spec.sort.by,
            ascending=spec.sort.direction is SortDirection.ASC,
            kind="stable",
        )
    # Sin orden explicito, un eje temporal se ordena cronologicamente: es lo que
    # cualquiera espera de una serie y evita graficos con el tiempo revuelto.
    if spec.x is not None and spec.x.key in frame.columns and spec.x.time_grain is not None:
        return frame.sort_values(spec.x.key, kind="stable")
    return frame


def _apply_limit(frame: pd.DataFrame, spec: VisualSpec) -> tuple[pd.DataFrame, bool]:
    if spec.limit is None or len(frame) <= spec.limit:
        return frame, False
    return frame.head(spec.limit), True


def _label_for(spec: VisualSpec, key: str) -> str:
    for dimension in spec.dimensions:
        if dimension.key == key and dimension.label:
            return dimension.label
    for measure in spec.y:
        if measure.key == key and measure.label:
            return measure.label
    return key


def _to_rows(frame: pd.DataFrame, keys: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    ordered = frame[list(keys)]
    records = ordered.astype(object).where(pd.notna(ordered), None).to_dict(orient="records")
    return tuple(
        {str(key): _jsonable(value) for key, value in record.items()} for record in records
    )


def _jsonable(value: Any) -> object:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat() if value == value.normalize() else value.isoformat()
    return value
