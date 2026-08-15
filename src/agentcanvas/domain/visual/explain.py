"""Traduce una `VisualSpec` al codigo Python que la calcula.

Existe para que el usuario pueda ver, y auditar, como se obtuvo cada numero.
Una especificacion declarativa es reproducible por construccion, pero eso hay
que poder comprobarlo: aqui se hace visible.

El codigo no es una aproximacion ni una ilustracion. Es el mismo algoritmo que
ejecuta el motor, paso por paso y en el mismo orden, y hay un test que ejecuta
lo que sale de aqui y compara el resultado con el del motor. Si alguna vez
divergen, ese test se pone rojo.
"""

from __future__ import annotations

from agentcanvas.domain.visual.spec import (
    Aggregation,
    ChartType,
    Dimension,
    Filter,
    FilterOperator,
    Operation,
    SortDirection,
    TimeGrain,
    VisualSpec,
)

_PANDAS_AGGREGATIONS: dict[Aggregation, str] = {
    Aggregation.SUM: "sum",
    Aggregation.AVG: "mean",
    Aggregation.MIN: "min",
    Aggregation.MAX: "max",
    Aggregation.COUNT: "count",
    Aggregation.COUNT_DISTINCT: "nunique",
    Aggregation.MEDIAN: "median",
}

_PERIODS: dict[TimeGrain, str] = {
    TimeGrain.DAY: "D",
    TimeGrain.WEEK: "W",
    TimeGrain.MONTH: "M",
    TimeGrain.QUARTER: "Q",
    TimeGrain.YEAR: "Y",
}

ROW_MARKER = "__row__"


def as_python(spec: VisualSpec, *, source: str = "datos.parquet") -> str:
    """El calculo completo, listo para pegar en un cuaderno."""
    lines = [
        "import pandas as pd",
        "",
        f"df = pd.read_parquet({source!r})",
    ]
    if any(measure.field is None for measure in spec.y):
        lines += [
            "",
            "# Columna auxiliar para contar filas, incluidas las que tienen nulos",
            f"df[{ROW_MARKER!r}] = 1",
        ]

    lines += _computed_lines(spec)
    lines += _filter_lines(spec.filters)
    lines += _grain_lines(spec.dimensions)
    lines += _aggregation_lines(spec)
    lines += _sort_lines(spec)
    lines += _limit_lines(spec)
    return "\n".join(lines).rstrip() + "\n"


_OPERATORS: dict[Operation, str] = {
    Operation.ADD: "+",
    Operation.SUBTRACT: "-",
    Operation.MULTIPLY: "*",
    Operation.DIVIDE: "/",
}


def _computed_lines(spec: VisualSpec) -> list[str]:
    if not spec.computed:
        return []
    lines = ["", "# Columnas calculadas"]
    for computed in spec.computed:
        if computed.right_field is not None:
            right = f"df[{computed.right_field!r}]"
        else:
            right = repr(computed.right_value)
        # El `replace` no es adorno: dividir entre cero da infinito, y un
        # infinito estropea la escala del eje sin decir por que.
        lines.append(
            f"df[{computed.name!r}] = ("
            f"df[{computed.left!r}] {_OPERATORS[computed.operation]} {right}"
            f").replace([float('inf'), float('-inf')], pd.NA)"
        )
    return lines


def _filter_lines(filters: tuple[Filter, ...]) -> list[str]:
    if not filters:
        return []
    lines = ["", "# Filtros"]
    for filter in filters:
        lines.append(f"df = df[{_condition(filter)}]")
    return lines


def _condition(filter: Filter) -> str:
    column = f"df[{filter.field!r}]"
    operator = filter.operator
    comparisons = {
        FilterOperator.EQ: "==",
        FilterOperator.NE: "!=",
        FilterOperator.GT: ">",
        FilterOperator.GTE: ">=",
        FilterOperator.LT: "<",
        FilterOperator.LTE: "<=",
    }
    if operator in comparisons:
        return f"{column} {comparisons[operator]} {filter.value!r}"
    if operator is FilterOperator.IS_NULL:
        return f"{column}.isna()"
    if operator is FilterOperator.NOT_NULL:
        return f"{column}.notna()"
    if operator is FilterOperator.CONTAINS:
        return f"{column}.astype(str).str.contains({str(filter.value)!r}, case=False, na=False)"
    if operator is FilterOperator.IN:
        return f"{column}.isin({list(filter.values)!r})"
    if operator is FilterOperator.NOT_IN:
        return f"~{column}.isin({list(filter.values)!r})"
    low, high = filter.values
    return f"{column}.between({low!r}, {high!r})"


def _grain_lines(dimensions: tuple[Dimension, ...]) -> list[str]:
    temporal = [d for d in dimensions if d.time_grain is not None]
    if not temporal:
        return []
    lines = ["", "# Agrupacion temporal: cada fecha se lleva al inicio de su periodo"]
    for dimension in temporal:
        assert dimension.time_grain is not None
        period = _PERIODS[dimension.time_grain]
        lines.append(
            f"df[{dimension.key!r}] = ("
            f"pd.to_datetime(df[{dimension.field!r}])"
            f".dt.to_period({period!r}).dt.to_timestamp())"
        )
    return lines


def _aggregation_lines(spec: VisualSpec) -> list[str]:
    if spec.type is ChartType.BOX:
        assert spec.x is not None
        column = spec.y[0].field
        return [
            "",
            "# Las cinco cifras de cada caja",
            f"resultado = df.groupby({spec.x.key!r}, dropna=False, observed=True)[{column!r}].agg(",
            "    minimo='min',",
            "    q1=lambda valores: valores.quantile(0.25),",
            "    mediana='median',",
            "    q3=lambda valores: valores.quantile(0.75),",
            "    maximo='max',",
            ").reset_index()",
        ]

    if spec.is_raw:
        keys = [d.key for d in spec.dimensions] + [m.key for m in spec.y]
        return ["", "# Filas sin agregar", f"resultado = df[{keys!r}].copy()"]

    named = [
        f"    {measure.key}=({_source_column(measure.field)!r}, {_function(measure)!r}),"
        for measure in spec.y
    ]
    group_keys = [dimension.key for dimension in spec.dimensions]
    if not group_keys:
        lines = ["", "# Un solo numero: se agrega todo el conjunto"]
        totals = ", ".join(
            f"{measure.key!r}: df[{_source_column(measure.field)!r}].{_function(measure)}()"
            for measure in spec.y
        )
        lines.append(f"resultado = pd.DataFrame([{{{totals}}}])")
        return lines

    return [
        "",
        "# Agregacion",
        f"resultado = df.groupby({group_keys!r}, dropna=False, observed=True).agg(",
        *named,
        ").reset_index()",
    ]


def _source_column(field: str | None) -> str:
    return field if field is not None else ROW_MARKER


def _function(measure: object) -> str:
    from agentcanvas.domain.visual.spec import Measure

    assert isinstance(measure, Measure)
    if measure.field is None:
        # `count` sin columna cuenta filas: se suma la columna auxiliar.
        return "sum"
    return _PANDAS_AGGREGATIONS[measure.aggregation]


def _sort_lines(spec: VisualSpec) -> list[str]:
    if spec.sort is not None:
        ascending = spec.sort.direction is SortDirection.ASC
        return [
            "",
            "# Orden",
            f"resultado = resultado.sort_values({spec.sort.by!r}, "
            f"ascending={ascending}, kind='stable')",
        ]
    if spec.x is not None and spec.x.time_grain is not None:
        return [
            "",
            "# Sin orden explicito, un eje temporal va cronologicamente",
            f"resultado = resultado.sort_values({spec.x.key!r}, kind='stable')",
        ]
    return []


def _limit_lines(spec: VisualSpec) -> list[str]:
    if spec.limit is None:
        return []
    return ["", "# Recorte", f"resultado = resultado.head({spec.limit})"]
