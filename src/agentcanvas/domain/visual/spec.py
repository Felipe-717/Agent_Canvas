"""`VisualSpec`: la especificacion declarativa de una visualizacion.

Este modulo es el contrato central del sistema y cumple tres papeles a la vez:

1. Es lo que el usuario guarda cuando guarda un grafico (nunca los valores).
2. Es el JSON Schema que se le impone al LLM como structured output, asi que
   cada campo y cada docstring acaba condicionando lo que el modelo produce.
3. Es la entrada del motor de queries determinista.

Por eso no puede contener codigo, ni SQL, ni expresiones libres: solo datos
verificables contra el schema del dataset. Un modelo mas debil producira una
spec peor, nunca un dashboard roto.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ChartType(StrEnum):
    LINE = "line"
    BAR = "bar"
    AREA = "area"
    PIE = "pie"
    SCATTER = "scatter"
    KPI = "kpi"
    TABLE = "table"


class Aggregation(StrEnum):
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    MEDIAN = "median"
    NONE = "none"
    """Sin agregar: las filas salen crudas. Es lo que necesitan un scatter o
    una tabla de detalle. No se puede mezclar con medidas agregadas."""


class TimeGrain(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"

    @property
    def uses_values(self) -> bool:
        """Operadores que leen `values` en lugar de `value`."""
        return self in (FilterOperator.IN, FilterOperator.NOT_IN, FilterOperator.BETWEEN)

    @property
    def uses_no_operand(self) -> bool:
        return self in (FilterOperator.IS_NULL, FilterOperator.NOT_NULL)


Scalar = str | float | bool

# `extra="forbid"` en todo lo que el modelo rellena: si escribe "column" donde
# va "field", pydantic lo dice por su nombre. Ignorarlo en silencio dejaba una
# medida sin columna y un error que no explicaba la causa.
STRICT = ConfigDict(frozen=True, extra="forbid")


class Filter(BaseModel):
    model_config = STRICT

    field: str
    """Nombre normalizado de la columna del dataset."""

    operator: FilterOperator
    value: Scalar | None = None
    """Operando para los operadores de un solo valor."""

    values: tuple[Scalar, ...] = ()
    """Operandos para `in`, `not_in` y `between` (este ultimo espera dos)."""


class Dimension(BaseModel):
    """Eje categorico o temporal por el que se agrupa."""

    model_config = STRICT

    field: str
    time_grain: TimeGrain | None = None
    """Solo para columnas de fecha: agrupa por mes, ano, etc."""

    label: str | None = None

    @property
    def key(self) -> str:
        """Nombre de la columna en el resultado."""
        if self.time_grain is None:
            return self.field
        return f"{self.field}_{self.time_grain}"


class Measure(BaseModel):
    """Valor numerico que se representa."""

    model_config = STRICT

    field: str | None = None
    """Puede ser nulo unicamente con `count`, que cuenta filas."""

    aggregation: Aggregation = Aggregation.SUM
    label: str | None = None

    @property
    def key(self) -> str:
        if self.aggregation is Aggregation.NONE:
            return self.field or "value"
        if self.field is None:
            return "count"
        return f"{self.aggregation}_{self.field}"


class Sort(BaseModel):
    model_config = STRICT

    by: str
    """Clave del resultado: la de una dimension o la de una medida."""

    direction: SortDirection = SortDirection.DESC


class VisualSpec(BaseModel):
    model_config = STRICT

    type: ChartType
    title: str
    x: Dimension | None = None
    """Eje horizontal. Ausente en un KPI."""

    y: tuple[Measure, ...] = Field(default=(), max_length=8)
    group_by: Dimension | None = None
    """Divide los datos en series (una linea o un color por categoria)."""

    filters: tuple[Filter, ...] = ()
    sort: Sort | None = None
    limit: int | None = Field(default=None, ge=1, le=10_000)
    """Filas del resultado tras ordenar. Es el "top 10" del lenguaje natural."""

    @property
    def is_raw(self) -> bool:
        """True si la spec pide filas sin agregar."""
        return bool(self.y) and all(m.aggregation is Aggregation.NONE for m in self.y)

    @property
    def dimensions(self) -> tuple[Dimension, ...]:
        return tuple(d for d in (self.x, self.group_by) if d is not None)

    @property
    def referenced_fields(self) -> tuple[str, ...]:
        """Todas las columnas del dataset que la spec necesita leer."""
        fields = [dimension.field for dimension in self.dimensions]
        fields.extend(measure.field for measure in self.y if measure.field is not None)
        fields.extend(filter.field for filter in self.filters)
        return tuple(dict.fromkeys(fields))
