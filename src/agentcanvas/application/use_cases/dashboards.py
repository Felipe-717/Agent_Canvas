"""Casos de uso del dashboard.

`OpenDashboardUseCase` es el que da sentido a todo lo anterior: recalcula cada
visual guardado contra la version activa de su dataset. Ni una llamada al
modelo, ni un valor almacenado. Si un visual ha dejado de ser valido porque su
dataset cambio, se informa de ese visual y los demas se pintan igual: un
dashboard a medias es infinitamente mejor que una pantalla de error.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentcanvas.application.ports.query import QueryEnginePort
from agentcanvas.application.ports.repositories import (
    DashboardRepositoryPort,
    DatasetRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.domain.shared.errors import DomainError, NotFoundError
from agentcanvas.domain.visual.dashboard import Dashboard, Placement, Visual
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec


class RenderedVisual(BaseModel):
    model_config = ConfigDict(frozen=True)

    visual: Visual
    data: VisualData | None = None
    error: str | None = None
    """Por que no se pudo calcular. Excluyente con `data`."""


class DashboardView(BaseModel):
    model_config = ConfigDict(frozen=True)

    dashboard: Dashboard
    visuals: tuple[RenderedVisual, ...]


class DashboardService:
    """Agrupa las operaciones sobre dashboards.

    Van juntas porque comparten exactamente las mismas dependencias y siempre
    se usan en la misma pantalla; separarlas en cinco clases seria ceremonia.
    """

    def __init__(
        self,
        *,
        dashboards: DashboardRepositoryPort,
        datasets: DatasetRepositoryPort,
        storage: FileStoragePort,
        engine: QueryEnginePort,
        uow: UnitOfWorkPort,
    ) -> None:
        self._dashboards = dashboards
        self._datasets = datasets
        self._storage = storage
        self._engine = engine
        self._uow = uow

    async def create(self, owner_id: str, name: str) -> Dashboard:
        dashboard = Dashboard(owner_id=owner_id, name=name)
        await self._dashboards.add(dashboard)
        await self._uow.commit()
        return dashboard

    async def list_all(self, owner_id: str) -> list[Dashboard]:
        # No se llama `list`: dentro del cuerpo de la clase eso sombrea al
        # builtin y las anotaciones `-> list[...]` de los demas metodos pasan
        # a referirse a este metodo.
        return await self._dashboards.list_for_owner(owner_id)

    async def rename(self, owner_id: str, dashboard_id: str, name: str) -> Dashboard:
        dashboard = await self._require(owner_id, dashboard_id)
        await self._dashboards.rename(dashboard.id, name)
        await self._uow.commit()
        return dashboard.model_copy(update={"name": name})

    async def delete(self, owner_id: str, dashboard_id: str) -> None:
        await self._require(owner_id, dashboard_id)
        await self._dashboards.delete(dashboard_id)
        await self._uow.commit()

    async def add_visual(
        self,
        owner_id: str,
        dashboard_id: str,
        *,
        dataset_id: str,
        spec: VisualSpec,
        placement: Placement | None = None,
    ) -> Visual:
        await self._require(owner_id, dashboard_id)
        dataset = await self._datasets.get(dataset_id)
        if dataset is None or dataset.owner_id != owner_id:
            raise NotFoundError("dataset", dataset_id)

        existing = tuple(await self._dashboards.list_visuals(dashboard_id))
        dashboard = await self._require(owner_id, dashboard_id)
        visual = Visual(
            dashboard_id=dashboard_id,
            dataset_id=dataset_id,
            spec=spec,
            placement=(placement or dashboard.next_placement(existing)).clamped(),
        )
        await self._dashboards.add_visual(visual)
        await self._uow.commit()
        return visual

    async def move_visuals(
        self, owner_id: str, dashboard_id: str, placements: dict[str, Placement]
    ) -> list[Visual]:
        """Guarda el layout completo tras arrastrar o redimensionar."""
        await self._require(owner_id, dashboard_id)
        moved: list[Visual] = []
        for visual in await self._dashboards.list_visuals(dashboard_id):
            placement = placements.get(visual.id)
            if placement is None:
                continue
            updated = visual.moved_to(placement)
            await self._dashboards.update_visual(updated)
            moved.append(updated)
        await self._uow.commit()
        return moved

    async def remove_visual(self, owner_id: str, dashboard_id: str, visual_id: str) -> None:
        await self._require(owner_id, dashboard_id)
        visual = await self._dashboards.get_visual(visual_id)
        if visual is None or visual.dashboard_id != dashboard_id:
            raise NotFoundError("visual", visual_id)
        await self._dashboards.delete_visual(visual_id)
        await self._uow.commit()

    async def open(self, owner_id: str, dashboard_id: str) -> DashboardView:
        """Recalcula el dashboard entero contra los datos actuales."""
        dashboard = await self._require(owner_id, dashboard_id)
        rendered = [
            await self._render(visual)
            for visual in await self._dashboards.list_visuals(dashboard_id)
        ]
        return DashboardView(dashboard=dashboard, visuals=tuple(rendered))

    async def _render(self, visual: Visual) -> RenderedVisual:
        dataset = await self._datasets.get(visual.dataset_id)
        if dataset is None:
            return RenderedVisual(visual=visual, error="El conjunto de datos ya no existe")
        if dataset.current_version_id is None:
            return RenderedVisual(visual=visual, error="El conjunto de datos no tiene datos")
        version = await self._datasets.get_version(dataset.current_version_id)
        if version is None:
            return RenderedVisual(visual=visual, error="No se encuentra la version activa")

        try:
            data = self._engine.execute(
                visual.spec,
                source=self._storage.path_for(version.storage_key),
                schema=dataset.schema_,
            )
        except DomainError as error:
            # Un visual roto no puede tumbar el tablero entero.
            return RenderedVisual(visual=visual, error=str(error))
        return RenderedVisual(visual=visual, data=data)

    async def _require(self, owner_id: str, dashboard_id: str) -> Dashboard:
        dashboard = await self._dashboards.get(dashboard_id)
        if dashboard is None or dashboard.owner_id != owner_id:
            raise NotFoundError("dashboard", dashboard_id)
        return dashboard
