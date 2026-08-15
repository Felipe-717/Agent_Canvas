from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from agentcanvas.application.use_cases.ingest_file import IngestFileCommand
from agentcanvas.domain.shared.errors import NotFoundError
from agentcanvas.infrastructure.persistence.repositories import SqlAlchemyDatasetRepository
from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep
from agentcanvas.infrastructure.web.schemas import DatasetOut, IngestOut, VersionOut

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("", response_model=IngestOut, status_code=status.HTTP_201_CREATED)
async def upload(
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
    file: Annotated[UploadFile, File(description="CSV o XLSX")],
    dataset_id: Annotated[str | None, Form()] = None,
    name: Annotated[str | None, Form()] = None,
) -> IngestOut:
    """Sube un archivo.

    Sin `dataset_id` nace un dataset nuevo y su esquema queda como contrato.
    Con `dataset_id`, el archivo se valida contra ese contrato y, si encaja, se
    convierte en la version activa: eso es lo que actualiza los graficos ya
    guardados sobre ese dataset.
    """
    result = await container.ingest_file(session).execute(
        IngestFileCommand(
            owner_id=owner_id,
            filename=file.filename or "archivo",
            content=await file.read(),
            dataset_id=dataset_id,
            dataset_name=name,
        )
    )
    return IngestOut(
        dataset=DatasetOut.of(result.dataset),
        version=VersionOut.of(result.version),
        created_dataset=result.created_dataset,
        preview=[dict(row) for row in result.table.preview],
    )


@router.get("", response_model=list[DatasetOut])
async def list_datasets(session: SessionDep, owner_id: OwnerDep) -> list[DatasetOut]:
    datasets = await SqlAlchemyDatasetRepository(session).list_for_owner(owner_id)
    return [DatasetOut.of(dataset) for dataset in datasets]


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, session: SessionDep, owner_id: OwnerDep) -> DatasetOut:
    dataset = await SqlAlchemyDatasetRepository(session).get(dataset_id)
    if dataset is None or dataset.owner_id != owner_id:
        raise NotFoundError("dataset", dataset_id)
    return DatasetOut.of(dataset)


@router.get("/{dataset_id}/versions", response_model=list[VersionOut])
async def list_versions(
    dataset_id: str, session: SessionDep, owner_id: OwnerDep
) -> list[VersionOut]:
    repository = SqlAlchemyDatasetRepository(session)
    dataset = await repository.get(dataset_id)
    if dataset is None or dataset.owner_id != owner_id:
        raise NotFoundError("dataset", dataset_id)
    return [VersionOut.of(version) for version in await repository.list_versions(dataset_id)]
