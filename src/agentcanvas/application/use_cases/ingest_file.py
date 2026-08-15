"""Ingesta de un archivo: de bytes subidos a dataset consultable.

Cubre los dos caminos del documento de diseno con la misma logica:

  - sin `dataset_id`: nace un `Dataset` nuevo y el schema detectado *es* su contrato
  - con `dataset_id`: el archivo se valida contra el contrato existente y, si
    encaja, se convierte en la version activa (esto es lo que actualiza los
    dashboards guardados)
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
from agentcanvas.application.ports.tabular import NormalizedTable, TabularReaderPort
from agentcanvas.domain.dataset.entities import (
    SUPPORTED_EXTENSIONS,
    Dataset,
    DatasetVersion,
    StoredFile,
)
from agentcanvas.domain.shared.errors import (
    EmptyFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from agentcanvas.domain.shared.identifiers import new_id


class IngestFileCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_id: str
    filename: str
    content: bytes
    dataset_id: str | None = None
    """Si viene, el archivo se anade a ese dataset en vez de crear uno nuevo."""

    dataset_name: str | None = None


class IngestFileResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: Dataset
    version: DatasetVersion
    table: NormalizedTable
    created_dataset: bool


class IngestFileUseCase:
    def __init__(
        self,
        *,
        storage: FileStoragePort,
        reader: TabularReaderPort,
        files: StoredFileRepositoryPort,
        datasets: DatasetRepositoryPort,
        uow: UnitOfWorkPort,
    ) -> None:
        self._storage = storage
        self._reader = reader
        self._files = files
        self._datasets = datasets
        self._uow = uow

    async def execute(self, command: IngestFileCommand) -> IngestFileResult:
        extension = _validated_extension(command.filename)

        # El dataset destino se resuelve antes de tocar disco porque su id
        # forma parte de la ruta del Parquet.
        existing = await self._load_target_dataset(command)
        dataset_id = existing.id if existing is not None else new_id("ds")

        stored = self._store_original(command, extension)
        parquet_key = f"datasets/{dataset_id}/{stored.id}.parquet"
        table = self._reader.read(
            self._storage.path_for(stored.storage_key),
            destination=self._storage.path_for(parquet_key),
        )
        if table.row_count == 0:
            self._storage.delete(stored.storage_key)
            self._storage.delete(parquet_key)
            raise EmptyFileError(command.filename)

        dataset = existing or Dataset(
            id=dataset_id,
            owner_id=command.owner_id,
            name=command.dataset_name or PurePath(command.filename).stem,
            schema=table.schema_,
        )

        # Aqui es donde el dominio rechaza un archivo incompatible.
        version = dataset.new_version(
            source_file_id=stored.id,
            storage_key=parquet_key,
            row_count=table.row_count,
            incoming_schema=table.schema_,
        )
        dataset.activate(version)

        await self._files.add(stored)
        if existing is None:
            await self._datasets.add(dataset)
        else:
            await self._datasets.update(dataset)
        await self._datasets.add_version(version)
        await self._uow.commit()

        return IngestFileResult(
            dataset=dataset,
            version=version,
            table=table,
            created_dataset=existing is None,
        )

    async def _load_target_dataset(self, command: IngestFileCommand) -> Dataset | None:
        if command.dataset_id is None:
            return None
        dataset = await self._datasets.get(command.dataset_id)
        if dataset is None or dataset.owner_id != command.owner_id:
            raise NotFoundError("dataset", command.dataset_id)
        return dataset

    def _store_original(self, command: IngestFileCommand, extension: str) -> StoredFile:
        file_id = new_id("file")
        key = f"uploads/{file_id}{extension}"
        self._storage.save(command.content, key=key)
        return StoredFile(
            id=file_id,
            owner_id=command.owner_id,
            original_filename=command.filename,
            extension=extension,
            size_bytes=len(command.content),
            checksum=hashlib.sha256(command.content).hexdigest(),
            storage_key=key,
        )


def _validated_extension(filename: str) -> str:
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(filename, SUPPORTED_EXTENSIONS)
    return extension
