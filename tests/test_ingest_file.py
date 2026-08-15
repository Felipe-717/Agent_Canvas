"""Ingesta de extremo a extremo: bytes -> SQLite + Parquet.

Sin mocks: storage real sobre tmp_path, lector real y SQLite real. Lo unico
simulado son los archivos.
"""

from __future__ import annotations

import pytest

from agentcanvas.application.use_cases.ingest_file import IngestFileCommand, IngestFileResult
from agentcanvas.bootstrap.container import Container
from agentcanvas.domain.dataset.entities import Dataset, DatasetVersion
from agentcanvas.domain.dataset.errors import SchemaMismatchError
from agentcanvas.domain.shared.errors import (
    EmptyFileError,
    NotFoundError,
    UnsupportedFileTypeError,
)
from agentcanvas.infrastructure.persistence.repositories import SqlAlchemyDatasetRepository
from tests.conftest import OWNER

ENERO = b"fecha,region,valor\n2026-01-15,Norte,100.0\n2026-01-20,Sur,150.0\n"
FEBRERO = b"fecha,region,valor\n2026-02-10,Norte,120.0\n2026-02-11,Sur,90.0\n2026-02-12,Este,60.0\n"
SIN_VALOR = b"fecha,region\n2026-03-01,Norte\n"


async def _ingest(
    container: Container,
    content: bytes,
    *,
    filename: str = "ventas.csv",
    dataset_id: str | None = None,
) -> IngestFileResult:
    session = container.session_factory()
    try:
        return await container.ingest_file(session).execute(
            IngestFileCommand(
                owner_id=OWNER,
                filename=filename,
                content=content,
                dataset_id=dataset_id,
            )
        )
    finally:
        await session.close()


async def _reload(container: Container, dataset_id: str) -> Dataset | None:
    session = container.session_factory()
    try:
        return await SqlAlchemyDatasetRepository(session).get(dataset_id)
    finally:
        await session.close()


async def _versions(container: Container, dataset_id: str) -> list[DatasetVersion]:
    session = container.session_factory()
    try:
        return await SqlAlchemyDatasetRepository(session).list_versions(dataset_id)
    finally:
        await session.close()


async def _compatible_with(container: Container, fingerprint: str) -> list[Dataset]:
    session = container.session_factory()
    try:
        return await SqlAlchemyDatasetRepository(session).find_compatible(OWNER, fingerprint)
    finally:
        await session.close()


async def test_first_upload_creates_the_dataset_and_its_contract(container: Container) -> None:
    result = await _ingest(container, ENERO)

    assert result.created_dataset
    assert result.dataset.name == "ventas"
    assert result.dataset.owner_id == OWNER
    assert result.dataset.schema_.column_names == ("fecha", "region", "valor")
    assert result.dataset.row_count == 2
    assert result.dataset.current_version_id == result.version.id


async def test_the_original_file_and_the_parquet_are_both_stored(container: Container) -> None:
    result = await _ingest(container, ENERO)

    assert container.storage.exists(result.version.storage_key)
    uploads = list(container.settings.uploads_dir.iterdir())
    assert len(uploads) == 1
    # El original se guarda intacto: es la fuente de verdad auditable.
    assert uploads[0].read_bytes() == ENERO


async def test_a_compatible_file_becomes_a_new_version_of_the_same_dataset(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)
    febrero = await _ingest(container, FEBRERO, dataset_id=enero.dataset.id)

    assert not febrero.created_dataset
    assert febrero.dataset.id == enero.dataset.id
    assert febrero.version.id != enero.version.id
    # Esto es lo que hace que un dashboard guardado se actualice solo.
    assert febrero.dataset.current_version_id == febrero.version.id
    assert febrero.dataset.row_count == 3


async def test_an_incompatible_file_is_rejected_naming_the_missing_column(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)

    with pytest.raises(SchemaMismatchError) as error:
        await _ingest(container, SIN_VALOR, dataset_id=enero.dataset.id)

    assert error.value.compatibility.missing_columns == ("valor",)
    assert "valor" in str(error.value)


async def test_the_dataset_keeps_its_previous_version_after_a_rejection(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)

    with pytest.raises(SchemaMismatchError):
        await _ingest(container, SIN_VALOR, dataset_id=enero.dataset.id)

    stored = await _reload(container, enero.dataset.id)
    assert stored is not None
    assert stored.current_version_id == enero.version.id
    assert stored.row_count == 2


async def test_versions_accumulate_in_history(container: Container) -> None:
    enero = await _ingest(container, ENERO)
    await _ingest(container, FEBRERO, dataset_id=enero.dataset.id)

    assert len(await _versions(container, enero.dataset.id)) == 2


async def test_a_dataset_can_be_found_by_the_fingerprint_of_a_new_file(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)

    matches = await _compatible_with(container, enero.dataset.fingerprint)

    assert [dataset.id for dataset in matches] == [enero.dataset.id]


async def test_unsupported_extension_is_rejected_before_touching_disk(
    container: Container,
) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        await _ingest(container, b"cualquier cosa", filename="informe.pdf")

    assert not any(container.settings.uploads_dir.iterdir())


async def test_a_file_with_headers_but_no_rows_is_rejected(container: Container) -> None:
    with pytest.raises(EmptyFileError):
        await _ingest(container, b"fecha,region,valor\n")


async def test_uploading_to_an_unknown_dataset_fails(container: Container) -> None:
    with pytest.raises(NotFoundError):
        await _ingest(container, ENERO, dataset_id="ds_inexistente")


async def test_the_schema_survives_the_round_trip_through_sqlite(container: Container) -> None:
    enero = await _ingest(container, ENERO)

    stored = await _reload(container, enero.dataset.id)

    assert stored is not None
    # El schema vuelve como objeto de dominio, no como dict.
    assert stored.schema_ == enero.dataset.schema_
    assert stored.fingerprint == enero.dataset.fingerprint
