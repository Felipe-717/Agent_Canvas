"""Validacion de una `VisualSpec` contra el schema de un dataset.

Es la barrera que separa "el modelo se equivoco" de "el dashboard se rompio".
Todo lo que el LLM invente (una columna que no existe, sumar texto, un KPI con
tres medidas) muere aqui, antes de tocar los datos, y con un mensaje que se le
puede devolver para que se corrija.
"""

from __future__ import annotations

from collections.abc import Callable

from agentcanvas.domain.dataset.schema import ColumnType, DatasetSchema
from agentcanvas.domain.visual.errors import InvalidVisualSpecError
from agentcanvas.domain.visual.spec import (
    Aggregation,
    ChartType,
    Dimension,
    FilterOperator,
    Measure,
    VisualSpec,
)

# Agregaciones que exigen una columna numerica.
_NUMERIC_ONLY = (Aggregation.SUM, Aggregation.AVG, Aggregation.MEDIAN)


def canonicalize(spec: VisualSpec, schema: DatasetSchema) -> VisualSpec:
    """Reescribe los nombres de columna a su forma normalizada.

    La validacion siempre normalizo al comprobar si una columna existe, asi que
    una spec que dijera "PetalLengthCm" pasaba el control; la ejecucion, en
    cambio, usaba el nombre crudo y reventaba al leer el Parquet. Normalizar
    aqui cierra esa grieta para todos los caminos a la vez, y es inocuo cuando
    la spec ya venia bien.
    """

    def name(field: str) -> str:
        column = schema.get(field)
        return column.name if column is not None else field

    return spec.model_copy(
        update={
            "x": _renamed_dimension(spec.x, name),
            "group_by": _renamed_dimension(spec.group_by, name),
            "y": tuple(
                measure.model_copy(update={"field": name(measure.field)})
                if measure.field is not None
                else measure
                for measure in spec.y
            ),
            "filters": tuple(
                filter.model_copy(update={"field": name(filter.field)})
                for filter in spec.filters
            ),
        }
    )


def _renamed_dimension(
    dimension: Dimension | None, name: Callable[[str], str]
) -> Dimension | None:
    if dimension is None:
        return None
    return dimension.model_copy(update={"field": name(dimension.field)})


def validate_spec(spec: VisualSpec, schema: DatasetSchema) -> tuple[str, ...]:
    """Devuelve los problemas encontrados. Vacio significa que la spec es valida."""
    problems: list[str] = []
    problems += _unknown_fields(spec, schema)
    if problems:
        # Sin columnas validas, el resto de comprobaciones solo generaria ruido.
        return tuple(problems)
    problems += _measure_problems(spec, schema)
    problems += _dimension_problems(spec, schema)
    problems += _chart_shape_problems(spec)
    problems += _filter_problems(spec)
    problems += _sort_problems(spec)
    return tuple(problems)


def ensure_valid(spec: VisualSpec, schema: DatasetSchema) -> None:
    problems = validate_spec(spec, schema)
    if problems:
        raise InvalidVisualSpecError(problems)


def _unknown_fields(spec: VisualSpec, schema: DatasetSchema) -> list[str]:
    available = ", ".join(schema.column_names)
    return [
        f"La columna '{field}' no existe en el dataset. Columnas disponibles: {available}"
        for field in spec.referenced_fields
        if not schema.has(field)
    ]


def _measure_problems(spec: VisualSpec, schema: DatasetSchema) -> list[str]:
    problems: list[str] = []
    aggregated = [m for m in spec.y if m.aggregation is not Aggregation.NONE]
    if aggregated and len(aggregated) != len(spec.y):
        problems.append(
            "No se pueden mezclar medidas agregadas con medidas sin agregar "
            "en la misma visualizacion"
        )
    for measure in spec.y:
        problems += _single_measure_problems(measure, schema)
    keys = [measure.key for measure in spec.y]
    if len(set(keys)) != len(keys):
        problems.append("Hay dos medidas que producen la misma columna de resultado")
    return problems


def _single_measure_problems(measure: Measure, schema: DatasetSchema) -> list[str]:
    if measure.field is None:
        if measure.aggregation is not Aggregation.COUNT:
            # Nombrar la clave, no solo el concepto: sin esto el modelo probaba
            # "column", "alias" y "column_ref" antes de acertar con "field".
            return [
                f"La medida con agregacion '{measure.aggregation}' no dice sobre que "
                f"columna se calcula: pon el nombre de la columna en el campo `field`"
            ]
        return []
    column = schema.get(measure.field)
    if column is None:
        return []
    if measure.aggregation in _NUMERIC_ONLY and not column.type.is_numeric:
        return [
            f"No se puede aplicar '{measure.aggregation}' sobre '{measure.field}', "
            f"que es de tipo {column.type}"
        ]
    return []


def _dimension_problems(spec: VisualSpec, schema: DatasetSchema) -> list[str]:
    problems: list[str] = []
    for dimension in spec.dimensions:
        column = schema.get(dimension.field)
        if column is None:
            continue
        if dimension.time_grain is not None and not column.type.is_temporal:
            problems.append(
                f"No se puede agrupar '{dimension.field}' por {dimension.time_grain}: "
                f"no es una columna de fecha (es {column.type})"
            )
    if spec.x is not None and spec.group_by is not None and spec.x.key == spec.group_by.key:
        problems.append("El eje y la agrupacion no pueden ser la misma columna")
    return problems


def _chart_shape_problems(spec: VisualSpec) -> list[str]:
    problems: list[str] = []
    measures = len(spec.y)

    if spec.type is ChartType.KPI:
        if measures != 1:
            problems.append("Un KPI necesita exactamente una medida")
        if spec.x is not None or spec.group_by is not None:
            problems.append("Un KPI no lleva eje ni agrupacion: es un solo numero")
        return problems

    if spec.type is ChartType.PIE:
        if measures != 1:
            problems.append("Un grafico de tarta necesita exactamente una medida")
        if spec.x is None:
            problems.append("Un grafico de tarta necesita una columna que defina las porciones")
        if spec.group_by is not None:
            problems.append("Un grafico de tarta no admite agrupacion adicional")
        return problems

    if spec.type is ChartType.SCATTER:
        if measures != 1:
            problems.append("Un scatter necesita exactamente una medida para el eje vertical")
        if spec.x is None:
            problems.append("Un scatter necesita un eje horizontal")
        if not spec.is_raw:
            problems.append(
                "Un scatter representa filas individuales: sus medidas deben usar "
                "la agregacion 'none'"
            )
        return problems

    if spec.type is ChartType.TABLE:
        if measures == 0 and not spec.dimensions:
            problems.append("Una tabla necesita al menos una columna")
        return problems

    # line, bar, area
    if spec.x is None:
        problems.append(f"Un grafico de tipo '{spec.type}' necesita un eje horizontal")
    if measures == 0:
        problems.append(f"Un grafico de tipo '{spec.type}' necesita al menos una medida")
    return problems


def _filter_problems(spec: VisualSpec) -> list[str]:
    problems: list[str] = []
    for filter in spec.filters:
        operator = filter.operator
        if operator.uses_no_operand:
            continue
        if operator is FilterOperator.BETWEEN and len(filter.values) != 2:
            problems.append(f"El filtro 'between' sobre '{filter.field}' necesita dos valores")
        elif operator.uses_values and not filter.values:
            problems.append(f"El filtro '{operator}' sobre '{filter.field}' necesita valores")
        elif not operator.uses_values and filter.value is None:
            problems.append(f"El filtro '{operator}' sobre '{filter.field}' necesita un valor")
    return problems


def _sort_problems(spec: VisualSpec) -> list[str]:
    if spec.sort is None:
        return []
    available = result_keys(spec)
    if spec.sort.by not in available:
        return [
            f"No se puede ordenar por '{spec.sort.by}': "
            f"el resultado solo tiene {', '.join(available)}"
        ]
    return []


def result_keys(spec: VisualSpec) -> tuple[str, ...]:
    """Columnas que tendra el resultado de ejecutar la spec."""
    keys = [dimension.key for dimension in spec.dimensions]
    keys.extend(measure.key for measure in spec.y)
    return tuple(dict.fromkeys(keys))


def result_type(spec: VisualSpec, key: str, schema: DatasetSchema) -> ColumnType:
    """Tipo de una columna del resultado."""
    for dimension in spec.dimensions:
        if dimension.key == key:
            column = schema.get(dimension.field)
            if column is None:
                return ColumnType.UNKNOWN
            # Agrupar por mes convierte un instante en una fecha.
            return ColumnType.DATE if dimension.time_grain is not None else column.type
    for measure in spec.y:
        if measure.key != key:
            continue
        if measure.aggregation in (Aggregation.COUNT, Aggregation.COUNT_DISTINCT):
            return ColumnType.INTEGER
        if measure.field is None:
            return ColumnType.INTEGER
        column = schema.get(measure.field)
        if column is None:
            return ColumnType.UNKNOWN
        if measure.aggregation is Aggregation.NONE:
            return column.type
        # Promediar o mediar enteros da decimales.
        if measure.aggregation in (Aggregation.AVG, Aggregation.MEDIAN):
            return ColumnType.FLOAT
        return column.type
    return ColumnType.UNKNOWN
