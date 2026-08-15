"""Actualizar un conjunto de datos con el archivo del mes siguiente.

Es la promesa entera del producto en un caso de uso: se relee el archivo nuevo
con exactamente las mismas coordenadas que se uso la primera vez, se comprueba
que el resultado sigue encajando en el contrato, y todos los graficos que
dependen de el pasan a mostrar los datos nuevos. Ni una llamada al modelo.

Si el archivo no encaja, no se toca nada. Un dashboard con datos viejos es
recuperable; uno con datos mal leidos, no.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePath

from pydantic import BaseModel, ConfigDict

from agentcanvas.application.ports.repositories import (
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.workbook import WorkbookReaderPort
from agentcanvas.domain.dataset.entities import Dataset, StoredFile
from agentcanvas.domain.shared.errors import DomainError, NotFoundError
from agentcanvas.domain.shared.identifiers import new_id
from agentcanvas.domain.workbook.structure import CSV_SHEET, TableSpec


class UnknownExtractionError(DomainError):
    """El conjunto se creo antes de que se guardara como se extrajo."""

    def __init__(self, dataset_name: str) -> None:
        super().__init__(
            f"No se sabe como se extrajo '{dataset_name}' del archivo original, "
            "asi que no se puede actualizar automaticamente. Vuelve a prepararlo "
            "desde el chat con el archivo nuevo."
        )


class RefreshResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: Dataset
    previous_rows: int

    @property
    def rows_added(self) -> int:
        return self.dataset.row_count - self.previous_rows


class RefreshDatasetUseCase:
    def __init__(
        self,
        *,
        datasets: DatasetRepositoryPort,
        files: StoredFileRepositoryPort,
        storage: FileStoragePort,
        workbook: WorkbookReaderPort,
        uow: UnitOfWorkPort,
    ) -> None:
        self._datasets = datasets
        self._files = files
        self._storage = storage
        self._workbook = workbook
        self._uow = uow

    async def execute(
        self, owner_id: str, dataset_id: str, *, filename: str, content: bytes
    ) -> RefreshResult:
        dataset = await self._datasets.get(dataset_id)
        if dataset is None or dataset.owner_id != owner_id:
            raise NotFoundError("dataset", dataset_id)

        spec = _spec_for(dataset, filename)
        stored = self._store(owner_id, filename, content)
        await self._files.add(stored)

        parquet_key = f"datasets/{dataset.id}/{stored.id}.parquet"
        table = self._workbook.extract(
            self._storage.path_for(stored.storage_key),
            spec,
            destination=self._storage.path_for(parquet_key),
        )

        previous = dataset.row_count
        # `new_version` valida el contrato y levanta si el archivo no encaja,
        # antes de que nada quede apuntando a los datos nuevos.
        version = dataset.new_version(
            source_file_id=stored.id,
            storage_key=parquet_key,
            row_count=table.row_count,
            incoming_schema=table.schema_,
        )
        dataset.activate(version)

        await self._datasets.update(dataset)
        await self._datasets.add_version(version)
        await self._uow.commit()
        return RefreshResult(dataset=dataset, previous_rows=previous)

    def _store(self, owner_id: str, filename: str, content: bytes) -> StoredFile:
        file_id = new_id("file")
        extension = PurePath(filename).suffix.lower() or ".bin"
        key = f"uploads/{file_id}{extension}"
        self._storage.save(content, key=key)
        return StoredFile(
            id=file_id,
            owner_id=owner_id,
            original_filename=filename,
            extension=extension,
            size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            storage_key=key,
        )


def _spec_for(dataset: Dataset, filename: str) -> TableSpec:
    """Las mismas coordenadas que la primera vez.

    Un CSV se relee siempre igual, asi que si el conjunto es antiguo y no las
    guardo, se puede reconstruir. Un Excel no: ahi hace falta preguntar.
    """
    if dataset.table_spec is not None:
        return dataset.table_spec
    if PurePath(filename).suffix.lower() in (".csv", ".txt", ".tsv"):
        return TableSpec(sheet=CSV_SHEET, header_row=1)
    raise UnknownExtractionError(dataset.name)
