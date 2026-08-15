"""El motor determinista: misma spec + mismos datos = mismo resultado."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.domain.dataset.schema import ColumnType
from agentcanvas.domain.visual.errors import InvalidVisualSpecError
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import (
    Aggregation,
    ChartType,
    Dimension,
    Filter,
    FilterOperator,
    Measure,
    Sort,
    SortDirection,
    TimeGrain,
    VisualSpec,
)
from agentcanvas.domain.workbook.structure import CSV_SHEET, TableSpec
from agentcanvas.infrastructure.query.pandas_engine import PandasQueryEngine
from agentcanvas.infrastructure.tabular.workbook_reader import OpenpyxlWorkbookReader

VENTAS = (
    b"fecha,region,producto,cantidad,valor\n"
    b"2026-01-15,Norte,A,2,100.0\n"
    b"2026-01-20,Sur,B,3,150.0\n"
    b"2026-02-10,Norte,A,1,120.0\n"
    b"2026-02-11,Sur,C,5,90.0\n"
    b"2026-02-12,Este,B,4,60.0\n"
    b"2026-03-05,Norte,B,2,200.0\n"
)


@pytest.fixture
def dataset(tmp_path: Path) -> tuple[Path, NormalizedTable]:
    source = tmp_path / "ventas.csv"
    source.write_bytes(VENTAS)
    parquet = tmp_path / "ventas.parquet"
    table = OpenpyxlWorkbookReader().extract(
        source, TableSpec(sheet=CSV_SHEET, header_row=1), destination=parquet
    )
    return parquet, table


def _run(dataset: tuple[Path, NormalizedTable], spec: VisualSpec) -> VisualData:
    parquet, table = dataset
    return PandasQueryEngine().execute(spec, source=parquet, schema=table.schema_)


def test_monthly_totals_are_grouped_and_ordered_chronologically(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="Ventas mensuales",
        x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    )

    data = _run(dataset, spec)

    assert [row["fecha_month"] for row in data.rows] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert [row["sum_valor"] for row in data.rows] == [250.0, 270.0, 200.0]


def test_grouping_produces_long_format_rows(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="Ventas por mes y region",
        x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        group_by=Dimension(field="region"),
    )

    data = _run(dataset, spec)

    assert {column.key for column in data.columns} == {"fecha_month", "region", "sum_valor"}
    enero_norte = [
        row
        for row in data.rows
        if row["fecha_month"] == "2026-01-01" and row["region"] == "Norte"
    ]
    assert enero_norte == [{"fecha_month": "2026-01-01", "region": "Norte", "sum_valor": 100.0}]


def test_a_kpi_collapses_everything_into_one_row(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="Venta total",
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    )

    data = _run(dataset, spec)

    assert data.rows == ({"sum_valor": 720.0},)


def test_count_without_a_column_counts_rows(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.KPI, title="Operaciones", y=(Measure(aggregation=Aggregation.COUNT),)
    )

    assert _run(dataset, spec).rows == ({"count": 6},)


def test_average_is_computed_per_group(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="Ticket medio por region",
        x=Dimension(field="region"),
        y=(Measure(field="valor", aggregation=Aggregation.AVG),),
    )

    data = _run(dataset, spec)
    by_region = {row["region"]: row["avg_valor"] for row in data.rows}

    assert by_region["Norte"] == pytest.approx(140.0)
    assert by_region["Este"] == pytest.approx(60.0)


def test_distinct_count_ignores_repetitions(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="Productos distintos",
        y=(Measure(field="producto", aggregation=Aggregation.COUNT_DISTINCT),),
    )

    assert _run(dataset, spec).rows == ({"count_distinct_producto": 3},)


def test_top_n_sorts_then_truncates_and_says_so(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="Top 2 regiones",
        x=Dimension(field="region"),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        sort=Sort(by="sum_valor", direction=SortDirection.DESC),
        limit=2,
    )

    data = _run(dataset, spec)

    assert [row["region"] for row in data.rows] == ["Norte", "Sur"]
    assert data.truncated


def test_a_limit_larger_than_the_result_does_not_mark_truncation(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"),),
        limit=50,
    )

    assert not _run(dataset, spec).truncated


@pytest.mark.parametrize(
    ("operator", "value", "values", "expected"),
    [
        (FilterOperator.EQ, "Norte", (), 420.0),
        (FilterOperator.NE, "Norte", (), 300.0),
        (FilterOperator.IN, None, ("Norte", "Este"), 480.0),
        (FilterOperator.NOT_IN, None, ("Norte", "Este"), 240.0),
        (FilterOperator.CONTAINS, "nort", (), 420.0),
    ],
)
def test_filters_on_a_text_column(
    dataset: tuple[Path, NormalizedTable],
    operator: FilterOperator,
    value: object,
    values: tuple[object, ...],
    expected: float,
) -> None:
    spec = VisualSpec(
        type=ChartType.KPI,
        title="x",
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        filters=(
            Filter(
                field="region",
                operator=operator,
                value=value,  # type: ignore[arg-type]
                values=values,  # type: ignore[arg-type]
            ),
        ),
    )

    assert _run(dataset, spec).rows[0]["sum_valor"] == pytest.approx(expected)


def test_a_date_filter_accepts_iso_text(dataset: tuple[Path, NormalizedTable]) -> None:
    # Las fechas llegan como texto desde el JSON de la spec; el motor las
    # convierte segun el tipo de la columna.
    spec = VisualSpec(
        type=ChartType.KPI,
        title="Febrero",
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        filters=(
            Filter(
                field="fecha",
                operator=FilterOperator.BETWEEN,
                values=("2026-02-01", "2026-02-28"),
            ),
        ),
    )

    assert _run(dataset, spec).rows[0]["sum_valor"] == pytest.approx(270.0)


def test_raw_mode_returns_individual_rows(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.SCATTER,
        title="Cantidad vs valor",
        x=Dimension(field="cantidad"),
        y=(Measure(field="valor", aggregation=Aggregation.NONE),),
    )

    data = _run(dataset, spec)

    assert len(data.rows) == 6
    assert data.rows[0] == {"cantidad": 2, "valor": 100.0}


def test_result_columns_carry_their_logical_type(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="region", label="RegiÃ³n"),
        y=(Measure(field="cantidad", aggregation=Aggregation.AVG, label="Media"),),
    )

    types = {column.key: column.type for column in _run(dataset, spec).columns}
    labels = {column.key: column.label for column in _run(dataset, spec).columns}

    assert types["region"] is ColumnType.STRING
    # Promediar enteros da decimales: el frontend necesita saberlo para formatear.
    assert types["avg_cantidad"] is ColumnType.FLOAT
    assert labels["region"] == "RegiÃ³n"
    assert labels["avg_cantidad"] == "Media"


def test_the_result_is_json_serialisable(dataset: tuple[Path, NormalizedTable]) -> None:
    spec = VisualSpec(
        type=ChartType.LINE,
        title="x",
        x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
        y=(Measure(field="valor"),),
    )

    json.dumps(_run(dataset, spec).rows)


def test_the_same_spec_twice_gives_the_identical_result(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    # La propiedad de la que depende todo el sistema de dashboards.
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor"), Measure(field="cantidad", aggregation=Aggregation.AVG)),
        sort=Sort(by="sum_valor"),
    )

    assert _run(dataset, spec) == _run(dataset, spec)


def test_an_invalid_spec_fails_before_reading_the_data(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.BAR,
        title="x",
        x=Dimension(field="inexistente"),
        y=(Measure(field="valor"),),
    )

    with pytest.raises(InvalidVisualSpecError) as error:
        _run(dataset, spec)

    assert "inexistente" in str(error.value)



def test_a_box_plot_summarises_each_category(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    spec = VisualSpec(
        type=ChartType.BOX,
        title="Reparto del valor por región",
        x=Dimension(field="region"),
        y=(Measure(field="valor", aggregation=Aggregation.NONE),),
    )

    data = _run(dataset, spec)

    assert [column.key for column in data.columns] == [
        "region", "minimo", "q1", "mediana", "q3", "maximo",
    ]
    norte = next(row for row in data.rows if row["region"] == "Norte")
    # Norte: 100, 120, 200.
    assert norte["minimo"] == 100.0
    assert norte["mediana"] == 120.0
    assert norte["maximo"] == 200.0
    # Los cuartiles interpolan, asi que el tipo es decimal aunque los datos
    # fueran enteros.
    assert all(
        column.type is ColumnType.FLOAT
        for column in data.columns
        if column.key != "region"
    )


def test_a_box_plot_needs_raw_values(dataset: tuple[Path, NormalizedTable]) -> None:
    # El resumen en cuartiles lo hace el propio grafico: pedir una suma encima
    # seria calcular dos veces.
    spec = VisualSpec(
        type=ChartType.BOX,
        title="x",
        x=Dimension(field="region"),
        y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    )

    with pytest.raises(InvalidVisualSpecError, match="none"):
        _run(dataset, spec)


def test_a_grouped_scatter_carries_its_category(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    # El grafico separa por categoria, asi que el resultado tiene que traerla:
    # sin ella el frontend pintaba todos los puntos del mismo color y el
    # grafico parecia correcto sin serlo.
    spec = VisualSpec(
        type=ChartType.SCATTER,
        title="Cantidad vs valor por región",
        x=Dimension(field="cantidad"),
        y=(Measure(field="valor", aggregation=Aggregation.NONE),),
        group_by=Dimension(field="region"),
    )

    data = _run(dataset, spec)

    assert "region" in [column.key for column in data.columns]
    assert {row["region"] for row in data.rows} == {"Norte", "Sur", "Este"}


def test_a_visualisation_admits_the_measures_a_summary_needs(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    # Media, mediana, minimo y maximo de cuatro columnas son dieciseis medidas.
    # Con el tope anterior de ocho, el modelo escribia la tabla a mano en el
    # mensaje: cifras sin artefacto, sin codigo y sin forma de comprobarlas.
    medidas = tuple(
        Measure(field=field, aggregation=aggregation)
        for field in ("valor", "cantidad")
        for aggregation in (
            Aggregation.AVG,
            Aggregation.MEDIAN,
            Aggregation.MIN,
            Aggregation.MAX,
        )
    )
    spec = VisualSpec(
        type=ChartType.TABLE, title="Resumen", x=Dimension(field="region"), y=medidas
    )

    data = _run(dataset, spec)

    assert len(data.columns) == 9  # la region mas las ocho medidas
