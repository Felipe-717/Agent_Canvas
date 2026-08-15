"""Tests del lector contra los desastres que traen los archivos reales."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.domain.dataset.schema import ColumnType
from agentcanvas.infrastructure.tabular.pandas_reader import PandasTabularReader


def _read(tmp_path: Path, name: str, content: bytes) -> NormalizedTable:
    source = tmp_path / name
    source.write_bytes(content)
    return PandasTabularReader().read(source, destination=tmp_path / "out.parquet")


def _types(table: NormalizedTable) -> dict[str, ColumnType]:
    return {column.name: column.type for column in table.schema_.columns}


def test_detects_semicolon_separator_and_latin1_accents(tmp_path: Path) -> None:
    content = "Fecha;Región;Valor\n2026-01-15;Antioquía;1200.5\n".encode("cp1252")
    table = _read(tmp_path, "ventas.csv", content)

    assert table.schema_.column_names == ("fecha", "region", "valor")
    assert table.row_count == 1


def test_infers_logical_types(tmp_path: Path) -> None:
    content = (
        b"fecha,producto,cantidad,valor,activo\n"
        b"2026-01-15,A,3,10.5,True\n"
        b"2026-02-20,B,4,12.0,False\n"
    )
    types = _types(_read(tmp_path, "v.csv", content))

    assert types["fecha"] is ColumnType.DATE
    assert types["producto"] is ColumnType.STRING
    assert types["cantidad"] is ColumnType.INTEGER
    assert types["valor"] is ColumnType.FLOAT
    assert types["activo"] is ColumnType.BOOLEAN


def test_a_timestamp_column_is_datetime_not_date(tmp_path: Path) -> None:
    content = b"momento,valor\n2026-01-15 08:30:00,1\n2026-01-15 14:00:00,2\n"
    assert _types(_read(tmp_path, "v.csv", content))["momento"] is ColumnType.DATETIME


def test_product_codes_that_look_like_dates_are_left_alone(tmp_path: Path) -> None:
    # "ABC-123" no, pero "12-3456" si cumple el patron de fecha corta.
    # Convertir a la ligera destruiria el dato.
    content = b"codigo,valor\nABC-123,1\nDEF-456,2\nGHI-789,3\n"
    assert _types(_read(tmp_path, "v.csv", content))["codigo"] is ColumnType.STRING


def test_duplicate_headers_are_disambiguated_not_lost(tmp_path: Path) -> None:
    table = _read(tmp_path, "v.csv", b"Valor,valor \n1,2\n")
    assert table.schema_.column_names == ("valor", "valor_2")


def test_original_names_are_preserved_for_display(tmp_path: Path) -> None:
    table = _read(tmp_path, "v.csv", b"Valor Total (USD),x\n1,2\n")

    column = table.schema_.get("valor_total_usd")
    assert column is not None
    assert column.original_name == "Valor Total (USD)"


def test_nullable_is_detected(tmp_path: Path) -> None:
    table = _read(tmp_path, "v.csv", b"a,b\n1,x\n,y\n")

    columns = {column.name: column for column in table.schema_.columns}
    assert columns["a"].nullable is True
    assert columns["b"].nullable is False


def test_writes_a_readable_parquet(tmp_path: Path) -> None:
    source = tmp_path / "v.csv"
    source.write_bytes(b"fecha,valor\n2026-01-15,10\n2026-02-15,20\n")
    destination = tmp_path / "nested" / "out.parquet"

    table = PandasTabularReader().read(source, destination=destination)

    frame = pd.read_parquet(destination)
    assert list(frame.columns) == ["fecha", "valor"]
    assert len(frame) == table.row_count == 2


def test_preview_is_json_serialisable(tmp_path: Path) -> None:
    table = _read(tmp_path, "v.csv", b"fecha,valor\n2026-01-15,10\n2026-02-15,\n")

    # Este preview va literalmente dentro del prompt del agente y del JSON de
    # la API: si contiene Timestamp o NaN, ambos revientan.
    json.dumps(table.preview)
    assert table.preview[1]["valor"] is None


def test_reads_xlsx(tmp_path: Path) -> None:
    source = tmp_path / "v.xlsx"
    pd.DataFrame({"Región": ["Norte"], "Valor": [10.5]}).to_excel(
        source, index=False, engine="openpyxl"
    )

    table = PandasTabularReader().read(source, destination=tmp_path / "out.parquet")

    assert table.schema_.column_names == ("region", "valor")
    assert table.row_count == 1
