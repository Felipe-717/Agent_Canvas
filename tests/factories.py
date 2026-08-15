"""Atajos para montar datos en los tests.

Preparar un conjunto de datos pasa por el chat, y hacerlo con el modelo
guionado en cada test que solo necesita "un dataset cualquiera" seria mucho
ruido para muy poca senal. Estos ayudantes hacen lo mismo por debajo.
"""

from __future__ import annotations

from agentcanvas.bootstrap.container import Container
from agentcanvas.domain.dataset.entities import Dataset
from agentcanvas.domain.shared.identifiers import new_id
from agentcanvas.domain.workbook.structure import CSV_SHEET, TableSpec
from agentcanvas.infrastructure.persistence.repositories import SqlAlchemyDatasetRepository


async def make_dataset(
    container: Container,
    *,
    name: str,
    csv: bytes,
    header_row: int = 1,
    owner_id: str | None = None,
) -> Dataset:
    """Crea un conjunto de datos a partir de un CSV, sin pasar por el chat.

    El dueno sale del contenedor salvo que se diga otro: inventarse uno
    distinto del que resuelve la API produce un 404 dificil de leer.
    """
    owner_id = owner_id or container.settings.default_owner_id
    dataset_id = new_id("ds")
    upload_key = f"uploads/{dataset_id}.csv"
    container.storage.save(csv, key=upload_key)

    parquet_key = f"datasets/{dataset_id}/tabla.parquet"
    table = container.workbook.extract(
        container.storage.path_for(upload_key),
        TableSpec(sheet=CSV_SHEET, header_row=header_row),
        destination=container.storage.path_for(parquet_key),
    )

    dataset = Dataset(id=dataset_id, owner_id=owner_id, name=name, schema=table.schema_)
    version = dataset.new_version(
        source_file_id=dataset_id,
        storage_key=parquet_key,
        row_count=table.row_count,
        incoming_schema=table.schema_,
    )
    dataset.activate(version)

    session = container.session_factory()
    try:
        repository = SqlAlchemyDatasetRepository(session)
        await repository.add(dataset)
        await repository.add_version(version)
        await session.commit()
    finally:
        await session.close()
    return dataset


async def add_version(container: Container, dataset: Dataset, csv: bytes) -> Dataset:
    """Sustituye los datos del conjunto por los de un archivo nuevo.

    Es lo que hace que un lienzo guardado se actualice solo, asi que conviene
    poder provocarlo en un test sin montar una conversacion entera.
    """
    upload_key = f"uploads/{new_id('file')}.csv"
    container.storage.save(csv, key=upload_key)
    parquet_key = f"datasets/{dataset.id}/{new_id('v')}.parquet"
    table = container.workbook.extract(
        container.storage.path_for(upload_key),
        TableSpec(sheet=CSV_SHEET, header_row=1),
        destination=container.storage.path_for(parquet_key),
    )
    version = dataset.new_version(
        source_file_id=dataset.id,
        storage_key=parquet_key,
        row_count=table.row_count,
        incoming_schema=table.schema_,
    )
    dataset.activate(version)

    session = container.session_factory()
    try:
        repository = SqlAlchemyDatasetRepository(session)
        await repository.update(dataset)
        await repository.add_version(version)
        await session.commit()
    finally:
        await session.close()
    return dataset
