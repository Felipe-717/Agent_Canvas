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
    BOX = "box"
    """Cajas y bigotes: resume la distribucion de una columna por categoria."""
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


class Operation(StrEnum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"


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

MAX_MEASURES = 16
"""Tope de medidas en una visualizacion.

Con ocho, una peticion tan corriente como "media, mediana, minimo y maximo
de cuatro columnas" no cabia, y el modelo se las apanaba escribiendo la
tabla a mano en el mensaje: cifras sin artefacto, sin codigo y sin forma de
comprobarlas."""

MAX_COMPUTED = 4
"""Tope de columnas calculadas. Con mas, lo que se esta pidiendo no es una
columna derivada sino una transformacion del dataset, y eso se prepara aparte."""


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


class Computed(BaseModel):
    """Una columna nueva, calculada fila a fila antes de filtrar y agregar.

    Existe porque preguntas de lo mas normales -"la proporcion entre largo y
    ancho del petalo", "el margen sobre el precio"- no se podian expresar, y el
    asistente tenia que decir que no. Con dos columnas y una operacion se cubre
    la mayoria.

    Deliberadamente no es una expresion libre: una operacion entre dos
    operandos, y cada operando es una columna del dataset o un numero. Admitir
    formulas obligaria a analizar y ejecutar texto que escribe un modelo, que es
    justo lo que este diseno evita. Encadenar operaciones tampoco: los operandos
    son siempre columnas reales, nunca otra columna calculada.
    """

    model_config = STRICT

    name: str
    """Nombre de la columna nueva. Se usa igual que una columna del dataset."""

    left: str
    """Columna del dataset sobre la que se opera."""

    operation: Operation

    right_field: str | None = None
    """El otro operando, si es otra columna."""

    right_value: float | None = None
    """El otro operando, si es un numero. Va uno de los dos, no ambos."""

    label: str | None = None


class Sort(BaseModel):
    model_config = STRICT

    by: str
    """Clave del resultado: la de una dimension o la de una medida."""

    direction: SortDirection = SortDirection.DESC


class VisualSpec(BaseModel):
    model_config = STRICT

    type: ChartType
    title: str
    computed: tuple[Computed, ...] = Field(default=(), max_length=MAX_COMPUTED)
    """Columnas derivadas que se crean antes de filtrar y agregar. El resto de
    la spec puede usarlas por su nombre igual que cualquier otra columna."""

    x: Dimension | None = None
    """Eje horizontal. Ausente en un KPI."""

    y: tuple[Measure, ...] = Field(default=(), max_length=MAX_MEASURES)
    group_by: Dimension | None = None
    """Divide los datos en series (una linea o un color por categoria)."""

    filters: tuple[Filter, ...] = ()
    sort: Sort | None = None
    limit: int | None = Field(default=None, ge=1, le=10_000)
    """Filas del resultado tras ordenar. Es el "top 10" del lenguaje natural."""

    @property
    def is_raw(self) -> bool:
        """True si la spec pide filas sin agregar.

        Una caja tambien declara sus medidas sin agregar -son los valores en
        crudo los que se resumen- pero no devuelve filas sueltas, asi que se
        excluye aqui.
        """
        if self.type is ChartType.BOX:
            return False
        return bool(self.y) and all(m.aggregation is Aggregation.NONE for m in self.y)

    @property
    def dimensions(self) -> tuple[Dimension, ...]:
        return tuple(d for d in (self.x, self.group_by) if d is not None)

    @property
    def computed_names(self) -> frozenset[str]:
        return frozenset(computed.name for computed in self.computed)

    @property
    def referenced_fields(self) -> tuple[str, ...]:
        """Las columnas del dataset que la spec necesita leer.

        Las calculadas quedan fuera: no existen en el archivo, se crean al
        vuelo. Sus operandos, en cambio, entran aqui, que es lo que hace que
        una formula sobre una columna inventada se detecte igual que el resto.
        """
        fields = [dimension.field for dimension in self.dimensions]
        fields.extend(measure.field for measure in self.y if measure.field is not None)
        fields.extend(filter.field for filter in self.filters)
        derived = self.computed_names
        for computed in self.computed:
            fields.append(computed.left)
            if computed.right_field is not None:
                fields.append(computed.right_field)
        # Un operando que nombre otra columna calculada tampoco se busca en el
        # archivo. No es que este permitido: es que la validacion tiene un
        # mensaje mucho mejor para ese caso que "esa columna no existe".
        return tuple(dict.fromkeys(f for f in fields if f not in derived))
