from __future__ import annotations

import pytest

from agentcanvas.domain.dataset.schema import (
    ColumnSchema,
    ColumnType,
    DatasetSchema,
    normalize_column_name,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Valor Total (USD) ", "valor_total_usd"),
        ("Región", "region"),
        ("Fecha de Emisión", "fecha_de_emision"),
        ("cantidad", "cantidad"),
        ("__Producto__", "producto"),
        ("Año/Mes", "ano_mes"),
    ],
)
def test_column_names_are_normalised(raw: str, expected: str) -> None:
    assert normalize_column_name(raw) == expected


def _schema(*columns: tuple[str, ColumnType]) -> DatasetSchema:
    return DatasetSchema(columns=tuple(ColumnSchema.create(name, type) for name, type in columns))


def test_fingerprint_ignores_column_order() -> None:
    a = _schema(("fecha", ColumnType.DATE), ("valor", ColumnType.FLOAT))
    b = _schema(("valor", ColumnType.FLOAT), ("fecha", ColumnType.DATE))
    assert a.fingerprint == b.fingerprint


def test_fingerprint_ignores_variations_within_a_type_family() -> None:
    # El mes que `cantidad` venga con decimales no debe cambiar la identidad
    # del dataset: seria un dashboard roto por un motivo trivial.
    integers = _schema(("cantidad", ColumnType.INTEGER))
    floats = _schema(("cantidad", ColumnType.FLOAT))
    assert integers.fingerprint == floats.fingerprint


def test_fingerprint_changes_when_a_column_disappears() -> None:
    full = _schema(("fecha", ColumnType.DATE), ("valor", ColumnType.FLOAT))
    partial = _schema(("fecha", ColumnType.DATE))
    assert full.fingerprint != partial.fingerprint


def test_missing_column_is_reported_with_its_name() -> None:
    contract = _schema(
        ("fecha", ColumnType.DATE), ("region", ColumnType.STRING), ("valor", ColumnType.FLOAT)
    )
    incoming = _schema(("fecha", ColumnType.DATE), ("region", ColumnType.STRING))

    result = contract.compare_with(incoming)

    assert not result.is_compatible
    assert result.missing_columns == ("valor",)
    assert "valor" in result.explain()


def test_extra_columns_do_not_break_compatibility() -> None:
    contract = _schema(("fecha", ColumnType.DATE), ("valor", ColumnType.FLOAT))
    incoming = _schema(
        ("fecha", ColumnType.DATE), ("valor", ColumnType.FLOAT), ("comentario", ColumnType.STRING)
    )

    result = contract.compare_with(incoming)

    assert result.is_compatible
    assert result.extra_columns == ("comentario",)


def test_a_numeric_column_arriving_as_text_is_a_mismatch() -> None:
    contract = _schema(("valor", ColumnType.FLOAT))
    incoming = _schema(("valor", ColumnType.STRING))

    result = contract.compare_with(incoming)

    assert not result.is_compatible
    assert result.type_mismatches == (("valor", ColumnType.FLOAT, ColumnType.STRING),)


def test_a_text_column_accepts_anything() -> None:
    contract = _schema(("codigo", ColumnType.STRING))
    incoming = _schema(("codigo", ColumnType.INTEGER))
    assert contract.compare_with(incoming).is_compatible


def test_lookup_normalises_the_requested_name() -> None:
    schema = _schema(("Valor Total", ColumnType.FLOAT))
    assert schema.has("  valor total  ")
    assert schema.get("VALOR_TOTAL") is not None
