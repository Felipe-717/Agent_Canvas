from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentcanvas.domain.dataset.entities import Dataset, DatasetVersion, StoredFile
from agentcanvas.infrastructure.persistence.models import (
    DatasetRow,
    DatasetVersionRow,
    StoredFileRow,
)


def aware(value: datetime) -> datetime:
    """SQLite no guarda zona horaria: se la devolvemos al salir.

    Sin esto, comparar `created_at` de una fila leida con `utcnow()` revienta
    con "can't compare offset-naive and offset-aware datetimes".
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlAlchemyUnitOfWork:
    """Implementa `UnitOfWorkPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class SqlAlchemyStoredFileRepository:
    """Implementa `StoredFileRepositoryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, file: StoredFile) -> None:
        self._session.add(
            StoredFileRow(
                id=file.id,
                owner_id=file.owner_id,
                original_filename=file.original_filename,
                extension=file.extension,
                size_bytes=file.size_bytes,
                checksum=file.checksum,
                storage_key=file.storage_key,
                created_at=file.created_at,
            )
        )
        await self._session.flush()

    async def get(self, file_id: str) -> StoredFile | None:
        row = await self._session.get(StoredFileRow, file_id)
        return _to_file(row) if row is not None else None

    async def find_by_checksum(self, owner_id: str, checksum: str) -> StoredFile | None:
        statement = select(StoredFileRow).where(
            StoredFileRow.owner_id == owner_id,
            StoredFileRow.checksum == checksum,
        )
        row = (await self._session.execute(statement)).scalars().first()
        return _to_file(row) if row is not None else None


class SqlAlchemyDatasetRepository:
    """Implementa `DatasetRepositoryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, dataset: Dataset) -> None:
        self._session.add(
            DatasetRow(
                id=dataset.id,
                owner_id=dataset.owner_id,
                name=dataset.name,
                schema_json=dataset.schema_,
                fingerprint=dataset.fingerprint,
                current_version_id=dataset.current_version_id,
                row_count=dataset.row_count,
                created_at=dataset.created_at,
                updated_at=dataset.updated_at,
            )
        )
        await self._session.flush()

    async def update(self, dataset: Dataset) -> None:
        row = await self._session.get(DatasetRow, dataset.id)
        if row is None:
            raise LookupError(f"El dataset {dataset.id} no existe")
        row.name = dataset.name
        row.schema_json = dataset.schema_
        row.fingerprint = dataset.fingerprint
        row.current_version_id = dataset.current_version_id
        row.row_count = dataset.row_count
        row.updated_at = dataset.updated_at
        await self._session.flush()

    async def get(self, dataset_id: str) -> Dataset | None:
        row = await self._session.get(DatasetRow, dataset_id)
        return _to_dataset(row) if row is not None else None

    async def list_for_owner(self, owner_id: str) -> list[Dataset]:
        statement = (
            select(DatasetRow)
            .where(DatasetRow.owner_id == owner_id)
            .order_by(DatasetRow.updated_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_dataset(row) for row in rows]

    async def find_compatible(self, owner_id: str, fingerprint: str) -> list[Dataset]:
        statement = (
            select(DatasetRow)
            .where(DatasetRow.owner_id == owner_id, DatasetRow.fingerprint == fingerprint)
            .order_by(DatasetRow.updated_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_dataset(row) for row in rows]

    async def add_version(self, version: DatasetVersion) -> None:
        self._session.add(
            DatasetVersionRow(
                id=version.id,
                dataset_id=version.dataset_id,
                source_file_id=version.source_file_id,
                storage_key=version.storage_key,
                row_count=version.row_count,
                schema_fingerprint=version.schema_fingerprint,
                created_at=version.created_at,
            )
        )
        await self._session.flush()

    async def get_version(self, version_id: str) -> DatasetVersion | None:
        row = await self._session.get(DatasetVersionRow, version_id)
        return _to_version(row) if row is not None else None

    async def list_versions(self, dataset_id: str) -> list[DatasetVersion]:
        statement = (
            select(DatasetVersionRow)
            .where(DatasetVersionRow.dataset_id == dataset_id)
            .order_by(DatasetVersionRow.created_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_version(row) for row in rows]


def _to_file(row: StoredFileRow) -> StoredFile:
    return StoredFile(
        id=row.id,
        owner_id=row.owner_id,
        original_filename=row.original_filename,
        extension=row.extension,
        size_bytes=row.size_bytes,
        checksum=row.checksum,
        storage_key=row.storage_key,
        created_at=aware(row.created_at),
    )


def _to_dataset(row: DatasetRow) -> Dataset:
    return Dataset(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        schema=row.schema_json,
        current_version_id=row.current_version_id,
        row_count=row.row_count,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )


def _to_version(row: DatasetVersionRow) -> DatasetVersion:
    return DatasetVersion(
        id=row.id,
        dataset_id=row.dataset_id,
        source_file_id=row.source_file_id,
        storage_key=row.storage_key,
        row_count=row.row_count,
        schema_fingerprint=row.schema_fingerprint,
        created_at=aware(row.created_at),
    )

