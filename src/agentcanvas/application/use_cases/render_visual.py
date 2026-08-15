"""Ejecuta una `VisualSpec` contra la version activa de un dataset.

Este caso de uso es el que se invoca tanto al crear un grafico como al
recalcular un dashboard entero tras subir un archivo nuevo. Que sea el mismo
codigo en ambos casos es intencionado: garantiza que un grafico guardado se
recalcule exactamente igual que se creo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentcanvas.application.ports.query import QueryEnginePort
from agentcanvas.application.ports.repositories import DatasetRepositoryPort
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.domain.shared.errors import DomainError, NotFoundError
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec


class DatasetHasNoDataError(DomainError):
    def __init__(self, dataset_name: str) -> None:
        super().__init__(f"El dataset '{dataset_name}' todavia no tiene datos cargados")
        self.dataset_name = dataset_name


class RenderVisualCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_id: str
    dataset_id: str
    spec: VisualSpec


class RenderVisualUseCase:
    def __init__(
        self,
        *,
        datasets: DatasetRepositoryPort,
        storage: FileStoragePort,
        engine: QueryEnginePort,
    ) -> None:
        self._datasets = datasets
        self._storage = storage
        self._engine = engine

    async def execute(self, command: RenderVisualCommand) -> VisualData:
        dataset = await self._datasets.get(command.dataset_id)
        if dataset is None or dataset.owner_id != command.owner_id:
            raise NotFoundError("dataset", command.dataset_id)
        if dataset.current_version_id is None:
            raise DatasetHasNoDataError(dataset.name)

        version = await self._datasets.get_version(dataset.current_version_id)
        if version is None:
            raise NotFoundError("version de dataset", dataset.current_version_id)

        return self._engine.execute(
            command.spec,
            source=self._storage.path_for(version.storage_key),
            schema=dataset.schema_,
        )
