"""Entidades del ciclo de vida de los datos.

Tres cosas distintas que el documento de diseno mezclaba y aqui van separadas:

    StoredFile      el archivo que subio el usuario, inmutable
    DatasetVersion  su forma normalizada (Parquet) tras una carga concreta
    Dataset         la entidad *logica* y estable a la que apuntan los visuales

Un visual guardado referencia el `Dataset`, nunca un archivo. Por eso subir el
Excel del mes siguiente actualiza el dashboard: crea una `DatasetVersion` nueva
bajo el mismo `Dataset`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.domain.dataset.errors import SchemaMismatchError
from agentcanvas.domain.dataset.schema import DatasetSchema
from agentcanvas.domain.shared.clock import utcnow
from agentcanvas.domain.shared.identifiers import new_id

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx")


class StoredFile(BaseModel):
    """Archivo original subido por el usuario. Nunca se modifica."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id("file"))
    owner_id: str
    original_filename: str
    extension: str
    size_bytes: int
    checksum: str
    """SHA-256 del contenido: detecta que el usuario resubio el mismo archivo."""

    storage_key: str
    created_at: datetime = Field(default_factory=utcnow)


class DatasetVersion(BaseModel):
    """Una carga concreta, ya normalizada a Parquet."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id("dsv"))
    dataset_id: str
    source_file_id: str
    storage_key: str
    """Ruta del Parquet normalizado dentro del almacenamiento."""

    row_count: int
    schema_fingerprint: str
    """Huella del archivo que la origino, para auditar por que se acepto."""

    created_at: datetime = Field(default_factory=utcnow)


class Dataset(BaseModel):
    """La entidad logica y estable. Es lo que referencian visuales y dashboards."""

    id: str = Field(default_factory=lambda: new_id("ds"))
    owner_id: str
    name: str
    schema_: DatasetSchema = Field(alias="schema")
    """`schema` colisiona con BaseModel.schema; el alias mantiene el JSON limpio."""

    current_version_id: str | None = None
    row_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    model_config = ConfigDict(populate_by_name=True)

    @property
    def fingerprint(self) -> str:
        return self.schema_.fingerprint

    def accepts(self, incoming: DatasetSchema) -> bool:
        return self.schema_.compare_with(incoming).is_compatible

    def new_version(
        self,
        *,
        source_file_id: str,
        storage_key: str,
        row_count: int,
        incoming_schema: DatasetSchema,
    ) -> DatasetVersion:
        """Crea una version nueva tras validar el contrato.

        Es el dominio, y no el caso de uso, quien decide si un archivo entra:
        la regla debe valer igual si manana la carga viene de una API o de un
        directorio vigilado.
        """
        compatibility = self.schema_.compare_with(incoming_schema)
        if not compatibility.is_compatible:
            raise SchemaMismatchError(self.name, compatibility)
        return DatasetVersion(
            dataset_id=self.id,
            source_file_id=source_file_id,
            storage_key=storage_key,
            row_count=row_count,
            schema_fingerprint=incoming_schema.fingerprint,
        )

    def activate(self, version: DatasetVersion) -> None:
        if version.dataset_id != self.id:
            raise ValueError("La version no pertenece a este dataset")
        self.current_version_id = version.id
        self.row_count = version.row_count
        self.updated_at = utcnow()
