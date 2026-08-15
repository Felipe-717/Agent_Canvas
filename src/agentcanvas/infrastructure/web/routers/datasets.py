from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


class RefreshOut(BaseModel):
    dataset_id: str
    name: str
    row_count: int
    previous_rows: int


@router.post("/{dataset_id}/refresh", response_model=RefreshOut)
async def refresh(
    dataset_id: str,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
    file: Annotated[UploadFile, File(description="El archivo nuevo")],
) -> RefreshOut:
    """Relee el archivo nuevo con las mismas coordenadas que la primera vez.

    Todos los graficos que dependen de este conjunto pasan a mostrar los datos
    nuevos sin volver a preguntarle nada al modelo. Si el archivo no encaja en
    el contrato, no se toca nada: un dashboard con datos viejos es recuperable,
    uno con datos mal leidos no.
    """
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("El archivo supera el tamano maximo admitido")

    result = await container.refresh_dataset(session).execute(
        owner_id,
        dataset_id,
        filename=file.filename or "archivo",
        content=content,
    )
    return RefreshOut(
        dataset_id=result.dataset.id,
        name=result.dataset.name,
        row_count=result.dataset.row_count,
        previous_rows=result.previous_rows,
    )
