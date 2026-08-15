"""Schema de un dataset tabular y su huella.

Esta es la pieza que hace posible la promesa del sistema: "sube el Excel del mes
siguiente y el dashboard se actualiza solo". Para poder afirmar que el archivo
nuevo *es el mismo dataset*, hace falta una definicion estable de "mismo
schema", y eso es `SchemaFingerprint`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class ColumnType(StrEnum):
    """Tipos logicos, no dtypes de pandas.

    El dominio no debe saber que existe `float64` ni `datetime64[ns]`; la
    traduccion ocurre en el adaptador que lee el archivo.
    """

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UNKNOWN = "unknown"

    @property
    def is_numeric(self) -> bool:
        return self in (ColumnType.INTEGER, ColumnType.FLOAT)

    @property
    def is_temporal(self) -> bool:
        return self in (ColumnType.DATE, ColumnType.DATETIME)

    def is_compatible_with(self, other: ColumnType) -> bool:
        """Puede una columna de tipo `other` ocupar el lugar de una de tipo self.

        Deliberadamente permisivo dentro de una misma familia: un mes en que la
        columna `cantidad` venga con decimales no debe romper el dashboard, y un
        Excel donde una fecha se leyo como datetime tampoco.
        """
        if self is other:
            return True
        if self.is_numeric and other.is_numeric:
            return True
        if self.is_temporal and other.is_temporal:
            return True
        # Todo es representable como texto, pero no al reves.
        return self is ColumnType.STRING


def normalize_column_name(raw: str) -> str:
    """`" Valor Total (USD) "` -> `valor_total_usd`.

    Los Excel reales traen acentos, mayusculas erraticas y espacios sobrantes
    que cambian entre meses. Comparar por el nombre crudo generaria falsos
    "schema incompatible" constantes.
    """
    decomposed = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub("_", ascii_only.strip().lower()).strip("_")


class ColumnSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    """Nombre normalizado. Es el que usan las VisualSpec y los scripts."""

    original_name: str
    """Nombre tal cual aparece en el archivo. Solo para mostrarlo al usuario."""

    type: ColumnType
    nullable: bool = True

    @classmethod
    def create(cls, original_name: str, type: ColumnType, *, nullable: bool = True) -> ColumnSchema:
        return cls(
            name=normalize_column_name(original_name),
            original_name=original_name,
            type=type,
            nullable=nullable,
        )


class SchemaCompatibility(BaseModel):
    """Resultado de contrastar un archivo nuevo contra el schema esperado."""

    model_config = ConfigDict(frozen=True)

    missing_columns: tuple[str, ...] = ()
    type_mismatches: tuple[tuple[str, ColumnType, ColumnType], ...] = ()
    """(columna, tipo esperado, tipo encontrado)."""

    extra_columns: tuple[str, ...] = ()
    """Columnas de mas. No invalidan nada: se ignoran."""

    @property
    def is_compatible(self) -> bool:
        return not self.missing_columns and not self.type_mismatches

    def explain(self) -> str:
        """Mensaje para el usuario final, no para el log."""
        if self.is_compatible:
            return "El archivo es compatible."
        parts: list[str] = ["Archivo incompatible."]
        if self.missing_columns:
            parts.append("Faltan las columnas: " + ", ".join(self.missing_columns))
        for column, expected, found in self.type_mismatches:
            parts.append(f"La columna '{column}' deberia ser {expected} y llego como {found}")
        return "\n".join(parts)


class DatasetSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: tuple[ColumnSchema, ...] = Field(min_length=1)

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def get(self, name: str) -> ColumnSchema | None:
        normalized = normalize_column_name(name)
        return next((c for c in self.columns if c.name == normalized), None)

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    @property
    def fingerprint(self) -> str:
        """Huella estable del schema.

        Depende del *conjunto* de columnas y sus tipos, no del orden: reordenar
        columnas en el Excel no debe romper la compatibilidad. Los tipos
        numericos y temporales colapsan a su familia para que un mes con
        decimales no cambie la huella.
        """
        parts = sorted(f"{c.name}:{_type_family(c.type)}" for c in self.columns)
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return digest[:16]

    def compare_with(self, incoming: DatasetSchema) -> SchemaCompatibility:
        """Contrasta un schema entrante contra este, que actua de contrato."""
        missing: list[str] = []
        mismatches: list[tuple[str, ColumnType, ColumnType]] = []
        for expected in self.columns:
            found = incoming.get(expected.name)
            if found is None:
                missing.append(expected.name)
            elif not expected.type.is_compatible_with(found.type):
                mismatches.append((expected.name, expected.type, found.type))
        extra = tuple(c.name for c in incoming.columns if not self.has(c.name))
        return SchemaCompatibility(
            missing_columns=tuple(missing),
            type_mismatches=tuple(mismatches),
            extra_columns=extra,
        )


def _type_family(type: ColumnType) -> str:
    if type.is_numeric:
        return "number"
    if type.is_temporal:
        return "temporal"
    return str(type)
