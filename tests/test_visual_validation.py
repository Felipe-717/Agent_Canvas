"""La spec se valida contra el schema antes de tocar datos.

Estos mensajes de error no son cosmeticos: son lo que se le devuelve al modelo
en el ciclo de correccion, asi que tienen que nombrar la columna culpable y las
disponibles.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentcanvas.domain.dataset.schema import ColumnSchema, ColumnType, DatasetSchema
from agentcanvas.domain.visual.spec import (
    Aggregation,
    ChartType,
    Computed,
    Dimension,
    Filter,
    FilterOperator,
    Measure,
    Operation,
    Sort,
    TimeGrain,
    VisualSpec,
)
from agentcanvas.domain.visual.validation import canonicalize, validate_spec

SCHEMA = DatasetSchema(
    columns=(
        ColumnSchema.create("fecha", ColumnType.DATE),
        ColumnSchema.create("region", ColumnType.STRING),
        ColumnSchema.create("valor", ColumnType.FLOAT),
        ColumnSchema.create("cantidad", ColumnType.INTEGER),
    )
)


def test_a_correct_spec_has_no_problems() -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="Ventas mensuales",
        x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    )
    assert validate_spec(spec, SCHEMA) == ()


def test_an_unknown_column_is_reported_with_the_available_ones() -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="departamento"),
        y=(Measure(field="valor"),),
    )

    problems = validate_spec(spec, SCHEMA)

    assert len(problems) == 1
    assert "departamento" in problems[0]
    # El modelo necesita saber que si existe para poder corregirse.
    assert "region" in problems[0]


def test_summing_a_text_column_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="fecha"),
        y=(Measure(field="region", aggregation=Aggregation.SUM),),
    )

    problems = validate_spec(spec, SCHEMA)

    assert any("region" in problem and "string" in problem for problem in problems)


def test_counting_a_text_column_is_fine() -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="fecha"),
        y=(Measure(field="region", aggregation=Aggregation.COUNT_DISTINCT),),
    )
    assert validate_spec(spec, SCHEMA) == ()


def test_grouping_a_non_date_column_by_month_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="x",
        x=Dimension(field="region", time_grain=TimeGrain.MONTH),
        y=(Measure(field="valor"),),
    )

    assert any("region" in problem for problem in validate_spec(spec, SCHEMA))


def test_a_kpi_with_an_axis_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"),),
    )
    assert validate_spec(spec, SCHEMA)


def test_a_kpi_with_one_measure_and_nothing_else_is_valid() -> None:
    spec = VisualSpec(type=ChartType.KPI, title="Total", y=(Measure(field="valor"),))
    assert validate_spec(spec, SCHEMA) == ()


def test_a_pie_with_two_measures_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.PIE,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"), Measure(field="cantidad")),
    )
    assert validate_spec(spec, SCHEMA)


def test_a_line_without_measures_is_rejected() -> None:
    spec = VisualSpec(type=ChartType.LINE, title="x", x=Dimension(field="fecha"))
    assert validate_spec(spec, SCHEMA)


def test_a_scatter_must_use_raw_values() -> None:
    aggregated = VisualSpec(
        type=ChartType.SCATTER,
        title="x",
        x=Dimension(field="cantidad"),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    )
    raw = VisualSpec(
        type=ChartType.SCATTER,
        title="x",
        x=Dimension(field="cantidad"),
        y=(Measure(field="valor", aggregation=Aggregation.NONE),),
    )

    assert validate_spec(aggregated, SCHEMA)
    assert validate_spec(raw, SCHEMA) == ()


def test_mixing_aggregated_and_raw_measures_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.TABLE,
        title="x",
        x=Dimension(field="region"),
        y=(
            Measure(field="valor", aggregation=Aggregation.SUM),
            Measure(field="cantidad", aggregation=Aggregation.NONE),
        ),
    )
    assert validate_spec(spec, SCHEMA)


def test_an_aggregation_without_a_column_is_rejected_unless_it_is_count() -> None:
    counting = VisualSpec(
        type=ChartType.KPI, title="x", y=(Measure(aggregation=Aggregation.COUNT),)
    )
    summing = VisualSpec(type=ChartType.KPI, title="x", y=(Measure(aggregation=Aggregation.SUM),))

    assert validate_spec(counting, SCHEMA) == ()
    assert validate_spec(summing, SCHEMA)


def test_sorting_by_something_absent_from_the_result_is_rejected() -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"),),
        sort=Sort(by="cantidad"),
    )

    problems = validate_spec(spec, SCHEMA)

    assert any("cantidad" in problem and "sum_valor" in problem for problem in problems)


def test_sorting_by_a_measure_key_is_accepted() -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"),),
        sort=Sort(by="sum_valor"),
    )
    assert validate_spec(spec, SCHEMA) == ()


def test_a_between_filter_needs_exactly_two_values() -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="x",
        y=(Measure(field="valor"),),
        filters=(Filter(field="valor", operator=FilterOperator.BETWEEN, values=(1.0,)),),
    )
    assert validate_spec(spec, SCHEMA)


def test_a_null_check_needs_no_operand() -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="x",
        y=(Measure(field="valor"),),
        filters=(Filter(field="region", operator=FilterOperator.IS_NULL),),
    )
    assert validate_spec(spec, SCHEMA) == ()


def test_the_axis_and_the_grouping_cannot_be_the_same_column() -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"),),
        group_by=Dimension(field="region"),
    )
    assert validate_spec(spec, SCHEMA)



def test_column_names_are_canonicalised_to_the_schema() -> None:
    # El modelo nombra las columnas como las ve en el archivo. La validacion
    # siempre normalizo al comprobar, pero la ejecucion usaba el nombre crudo:
    # la spec pasaba el control y reventaba despues al leer el Parquet.
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="Región"),
        y=(Measure(field="Valor Total", aggregation=Aggregation.SUM),),
        filters=(Filter(field="Región", operator=FilterOperator.EQ, value="Norte"),),
    )
    schema = DatasetSchema(
        columns=(
            ColumnSchema.create("Región", ColumnType.STRING),
            ColumnSchema.create("Valor Total", ColumnType.FLOAT),
        )
    )

    canonical = canonicalize(spec, schema)

    assert canonical.x is not None
    assert canonical.x.field == "region"
    assert canonical.y[0].field == "valor_total"
    assert canonical.filters[0].field == "region"


def test_canonicalising_an_already_correct_spec_changes_nothing() -> None:
    spec = VisualSpec(
        type=ChartType.KPI, title="x", y=(Measure(field="valor", aggregation=Aggregation.SUM),)
    )

    assert canonicalize(spec, SCHEMA) == spec


def test_an_unknown_column_survives_canonicalisation_to_be_reported() -> None:
    # Si se inventara un nombre, el error debe seguir diciendo cual.
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="departamento"),
        y=(Measure(field="valor"),),
    )

    problems = validate_spec(canonicalize(spec, SCHEMA), SCHEMA)

    assert any("departamento" in problem for problem in problems)


def test_an_invented_key_is_rejected_by_name() -> None:
    # El modelo escribia "column" donde va "field". Ignorarlo en silencio
    # dejaba una medida sin columna y un error que no explicaba la causa;
    # le costo ocho intentos dar con la clave correcta.
    with pytest.raises(ValidationError) as error:
        VisualSpec.model_validate(
            {
                "type": "kpi",
                "title": "x",
                "y": [{"column": "valor", "aggregation": "avg"}],
            }
        )

    assert "column" in str(error.value)


def test_a_measure_without_a_column_names_the_missing_key() -> None:
    spec = VisualSpec(type=ChartType.KPI, title="x", y=(Measure(aggregation=Aggregation.AVG),))

    problems = validate_spec(spec, SCHEMA)

    # Decir "necesita una columna" no basta: hay que decir como se llama.
    assert any("`field`" in problem for problem in problems)


# -------------------------------------------------------- columnas calculadas


def _ratio(**cambios: object) -> VisualSpec:
    campos: dict[str, object] = {
        "name": "valor_unitario",
        "left": "valor",
        "operation": Operation.DIVIDE,
        "right_field": "cantidad",
    }
    campos.update(cambios)
    return VisualSpec(
        type=ChartType.BAR,
        title="x",
        computed=(Computed(**campos),),  # type: ignore[arg-type]
        x=Dimension(field="region"),
        # La medida sigue al nombre: si no, cambiarlo dejaria la spec apuntando
        # a una columna que no existe y saltaria otro error antes que el suyo.
        y=(Measure(field=str(campos["name"]), aggregation=Aggregation.AVG),),
    )


def test_a_measure_can_use_a_computed_column() -> None:
    # La columna no esta en el schema y aun asi la spec es valida: se crea antes
    # de agregar. Sin esto, "la proporcion entre A y B" no se podia ni pedir.
    assert validate_spec(_ratio(), SCHEMA) == ()


def test_a_computed_column_cannot_shadow_a_real_one() -> None:
    problems = validate_spec(_ratio(name="valor"), SCHEMA)
    assert any("se llama igual que una columna del dataset" in p for p in problems)


def test_a_computed_column_cannot_operate_on_text() -> None:
    problems = validate_spec(_ratio(right_field="region"), SCHEMA)
    assert any("'region'" in p and "no un numero" in p for p in problems)


def test_a_computed_column_needs_exactly_one_second_operand() -> None:
    ninguno = validate_spec(_ratio(right_field=None), SCHEMA)
    assert any("exactamente un segundo operando" in p for p in ninguno)

    ambos = validate_spec(_ratio(right_value=2.0), SCHEMA)
    assert any("exactamente un segundo operando" in p for p in ambos)


def test_a_computed_column_cannot_divide_by_zero() -> None:
    problems = validate_spec(_ratio(right_field=None, right_value=0.0), SCHEMA)
    assert any("divide entre cero" in p for p in problems)


def test_computed_columns_cannot_be_chained() -> None:
    # Encadenarlas exigiria resolver dependencias y detectar ciclos, y ninguna
    # pregunta real lo pide. Mejor decirlo que resolverlo a medias.
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        computed=(
            Computed(
                name="unitario",
                left="valor",
                operation=Operation.DIVIDE,
                right_field="cantidad",
            ),
            Computed(
                name="doble",
                left="unitario",
                operation=Operation.MULTIPLY,
                right_value=2.0,
            ),
        ),
        x=Dimension(field="region"),
        y=(Measure(field="doble", aggregation=Aggregation.AVG),),
    )
    problems = validate_spec(spec, SCHEMA)
    assert any("tambien es calculada" in p for p in problems)


def test_an_operand_that_does_not_exist_is_reported() -> None:
    problems = validate_spec(_ratio(right_field="inventada"), SCHEMA)
    assert any("'inventada' no existe" in p for p in problems)


def test_canonicalize_normalises_the_operands() -> None:
    # La spec nombra las columnas como venian en el archivo; los operandos hay
    # que normalizarlos igual que el resto, o el motor no los encuentra.
    spec = _ratio(left="Valor", right_field="Cantidad")
    resultado = canonicalize(spec, SCHEMA)
    assert resultado.computed[0].left == "valor"
    assert resultado.computed[0].right_field == "cantidad"
    assert resultado.computed[0].name == "valor_unitario"
