"""El codigo que se le ensena al usuario tiene que ser el que se ejecuta.

Un "asi se calcula" que no coincide con el calculo real es peor que no dar
ninguno: da confianza sin merecerla. Por eso estos tests no comprueban que el
texto tenga buena pinta, sino que al ejecutarlo sale exactamente lo mismo que
devuelve el motor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.domain.visual.explain import as_python
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


def _run_generated(code: str) -> pd.DataFrame:
    scope: dict[str, Any] = {}
    exec(compile(code, "<explicacion>", "exec"), scope)
    resultado = scope["resultado"]
    assert isinstance(resultado, pd.DataFrame)
    return resultado


def _assert_matches(dataset: tuple[Path, NormalizedTable], spec: VisualSpec) -> None:
    """Ejecuta el codigo generado y lo compara con el motor, fila a fila."""
    parquet, table = dataset
    esperado = PandasQueryEngine().execute(spec, source=parquet, schema=table.schema_)
    obtenido = _run_generated(as_python(spec, source=str(parquet)))

    keys = [column.key for column in esperado.columns]
    filas = [
        {key: _plain(row[key]) for key in keys}
        for row in obtenido[keys].to_dict(orient="records")
    ]
    assert filas == [{key: _plain(row[key]) for key in keys} for row in esperado.rows]


def _plain(value: Any) -> Any:
    """Las fechas salen como Timestamp de un lado y como texto ISO del otro."""
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat() if value == value.normalize() else value.isoformat()
    if isinstance(value, float):
        return round(value, 9)
    return value


def test_a_grouped_sum_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BAR,
            title="x",
            x=Dimension(field="region"),
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        ),
    )


def test_a_monthly_series_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.LINE,
            title="x",
            x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
        ),
    )


def test_a_kpi_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.KPI,
            title="x",
            y=(Measure(field="valor", aggregation=Aggregation.AVG),),
        ),
    )


def test_counting_rows_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BAR,
            title="x",
            x=Dimension(field="region"),
            y=(Measure(aggregation=Aggregation.COUNT),),
        ),
    )


def test_a_top_n_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BAR,
            title="x",
            x=Dimension(field="region"),
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
            sort=Sort(by="sum_valor", direction=SortDirection.DESC),
            limit=2,
        ),
    )


def test_filters_match(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.KPI,
            title="x",
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
            filters=(
                Filter(field="region", operator=FilterOperator.IN, values=("Norte", "Este")),
                Filter(field="cantidad", operator=FilterOperator.GTE, value=2),
            ),
        ),
    )


def test_a_date_range_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.KPI,
            title="x",
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
            filters=(
                Filter(
                    field="fecha",
                    operator=FilterOperator.BETWEEN,
                    values=("2026-02-01", "2026-02-28"),
                ),
            ),
        ),
    )


def test_grouped_series_match(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.LINE,
            title="x",
            x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
            group_by=Dimension(field="region"),
        ),
    )


def test_raw_rows_match(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.SCATTER,
            title="x",
            x=Dimension(field="cantidad"),
            y=(Measure(field="valor", aggregation=Aggregation.NONE),),
        ),
    )


def test_several_measures_match(dataset: tuple[Path, NormalizedTable]) -> None:
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.TABLE,
            title="x",
            x=Dimension(field="region"),
            y=(
                Measure(field="valor", aggregation=Aggregation.SUM),
                Measure(field="cantidad", aggregation=Aggregation.AVG),
                Measure(field="producto", aggregation=Aggregation.COUNT_DISTINCT),
            ),
        ),
    )


def test_the_code_reads_like_something_a_person_would_write() -> None:
    code = as_python(
        VisualSpec(
            type=ChartType.LINE,
            title="x",
            x=Dimension(field="fecha", time_grain=TimeGrain.MONTH),
            y=(Measure(field="valor", aggregation=Aggregation.SUM),),
            limit=5,
        ),
        source="ventas.parquet",
    )

    # Se le ensena a un usuario, no a un compilador.
    assert code.startswith("import pandas as pd")
    assert "# Agregacion" in code
    assert "# Recorte" in code
    assert "ventas.parquet" in code


def test_a_box_plot_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    # Las cinco cifras tambien tienen que salir iguales por los dos caminos.
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BOX,
            title="x",
            x=Dimension(field="region"),
            y=(Measure(field="valor", aggregation=Aggregation.NONE),),
        ),
    )


def test_a_computed_column_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    # El valor unitario no esta en el archivo: sale de dividir dos columnas.
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BAR,
            title="x",
            computed=(
                Computed(
                    name="valor_unitario",
                    left="valor",
                    operation=Operation.DIVIDE,
                    right_field="cantidad",
                ),
            ),
            x=Dimension(field="region"),
            y=(Measure(field="valor_unitario", aggregation=Aggregation.AVG),),
        ),
    )


def test_a_computed_column_in_a_box_matches(dataset: tuple[Path, NormalizedTable]) -> None:
    # Una caja sobre una columna que no existe hasta que se calcula.
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BOX,
            title="x",
            computed=(
                Computed(
                    name="valor_unitario",
                    left="valor",
                    operation=Operation.DIVIDE,
                    right_field="cantidad",
                ),
            ),
            x=Dimension(field="region"),
            y=(Measure(field="valor_unitario", aggregation=Aggregation.NONE),),
        ),
    )


def test_a_computed_column_filtered_and_sorted_matches(
    dataset: tuple[Path, NormalizedTable],
) -> None:
    # Filtrar por la columna calculada obliga a crearla antes de filtrar; si el
    # orden de los pasos divergiera entre motor y codigo, esto se pondria rojo.
    _assert_matches(
        dataset,
        VisualSpec(
            type=ChartType.BAR,
            title="x",
            computed=(
                Computed(
                    name="valor_doble",
                    left="valor",
                    operation=Operation.MULTIPLY,
                    right_value=2,
                ),
            ),
            filters=(Filter(field="valor_doble", operator=FilterOperator.GT, value=150),),
            x=Dimension(field="producto"),
            y=(Measure(field="valor_doble", aggregation=Aggregation.SUM),),
            sort=Sort(by="sum_valor_doble", direction=SortDirection.DESC),
        ),
    )
