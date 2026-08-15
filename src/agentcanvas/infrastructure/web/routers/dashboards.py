from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from agentcanvas.application.use_cases.dashboards import (
    DashboardView,
    DatasetRef,
    RenderedVisual,
)
from agentcanvas.domain.visual.dashboard import GRID_COLUMNS, Dashboard, Placement
from agentcanvas.domain.visual.explain import as_python
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


class SourceOut(BaseModel):
    id: str
    name: str
    row_count: int = 0
    can_refresh: bool = True

    @classmethod
    def of(cls, source: DatasetRef) -> SourceOut:
        return cls(
            id=source.id,
            name=source.name,
            row_count=source.row_count,
            can_refresh=source.can_refresh,
        )


class DashboardIn(BaseModel):
    name: str = Field(default="Sin titulo", min_length=1, max_length=120)


class AddVisualIn(BaseModel):
    dataset_id: str
    spec: VisualSpec
    placement: Placement | None = None


class LayoutItemIn(BaseModel):
    visual_id: str
    placement: Placement


class LayoutIn(BaseModel):
    items: list[LayoutItemIn]


class DashboardOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, dashboard: Dashboard) -> DashboardOut:
        return cls(
            id=dashboard.id,
            name=dashboard.name,
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
        )


class VisualOut(BaseModel):
    id: str
    dataset_id: str
    spec: VisualSpec
    placement: Placement
    data: VisualData | None = None
    code: str | None = None
    """El calculo exacto en Python, generado de la spec."""

    error: str | None = None

    @classmethod
    def of(cls, rendered: RenderedVisual) -> VisualOut:
        visual = rendered.visual
        return cls(
            id=visual.id,
            dataset_id=visual.dataset_id,
            spec=visual.spec,
            placement=visual.placement,
            data=rendered.data,
            code=as_python(visual.spec),
            error=rendered.error,
        )


class DashboardDetailOut(BaseModel):
    dashboard: DashboardOut
    visuals: list[VisualOut]
    sources: list[SourceOut]
    """De que conjuntos bebe. Se actualizan uno a uno desde la cabecera."""

    grid_columns: int = GRID_COLUMNS
    """El frontend necesita la misma rejilla que el dominio para no descuadrar."""

    @classmethod
    def of(cls, view: DashboardView) -> DashboardDetailOut:
        return cls(
            dashboard=DashboardOut.of(view.dashboard),
            visuals=[VisualOut.of(rendered) for rendered in view.visuals],
            sources=[SourceOut.of(source) for source in view.sources],
        )


@router.post("", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: DashboardIn, container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> DashboardOut:
    return DashboardOut.of(await container.dashboards(session).create(owner_id, body.name))


class DashboardListItemOut(BaseModel):
    """Un lienzo en la lista, con las fuentes de las que bebe.

    Se exponen para poder agrupar la lista por origen sin obligar a que un
    lienzo pertenezca a uno solo: puede mezclar varios.
    """

    id: str
    name: str
    visual_count: int
    sources: list[SourceOut]
    updated_at: datetime


@router.get("", response_model=list[DashboardListItemOut])
async def list_dashboards(
    container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> list[DashboardListItemOut]:
    summaries = await container.dashboards(session).list_all(owner_id)
    return [
        DashboardListItemOut(
            id=summary.dashboard.id,
            name=summary.dashboard.name,
            visual_count=summary.visual_count,
            sources=[SourceOut.of(source) for source in summary.sources],
            updated_at=summary.dashboard.updated_at,
        )
        for summary in summaries
    ]


@router.get("/{dashboard_id}", response_model=DashboardDetailOut)
async def open_dashboard(
    dashboard_id: str, container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> DashboardDetailOut:
    """Abre el dashboard recalculando cada visual contra los datos actuales.

    No hay ningun valor almacenado que devolver: se calculan aqui, siempre.
    """
    return DashboardDetailOut.of(await container.dashboards(session).open(owner_id, dashboard_id))


@router.patch("/{dashboard_id}", response_model=DashboardOut)
async def rename(
    dashboard_id: str,
    body: DashboardIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> DashboardOut:
    service = container.dashboards(session)
    return DashboardOut.of(await service.rename(owner_id, dashboard_id, body.name))


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    dashboard_id: str, container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> None:
    await container.dashboards(session).delete(owner_id, dashboard_id)


@router.post("/{dashboard_id}/visuals", response_model=VisualOut, status_code=201)
async def add_visual(
    dashboard_id: str,
    body: AddVisualIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> VisualOut:
    visual = await container.dashboards(session).add_visual(
        owner_id,
        dashboard_id,
        dataset_id=body.dataset_id,
        spec=body.spec,
        placement=body.placement,
    )
    return VisualOut(
        id=visual.id,
        dataset_id=visual.dataset_id,
        spec=visual.spec,
        placement=visual.placement,
    )


@router.put("/{dashboard_id}/layout", response_model=list[VisualOut])
async def save_layout(
    dashboard_id: str,
    body: LayoutIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> list[VisualOut]:
    """Guarda posiciones y tamanos tras arrastrar o redimensionar."""
    moved = await container.dashboards(session).move_visuals(
        owner_id,
        dashboard_id,
        {item.visual_id: item.placement for item in body.items},
    )
    return [
        VisualOut(
            id=visual.id,
            dataset_id=visual.dataset_id,
            spec=visual.spec,
            placement=visual.placement,
        )
        for visual in moved
    ]


@router.delete(
    "/{dashboard_id}/visuals/{visual_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_visual(
    dashboard_id: str,
    visual_id: str,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> None:
    await container.dashboards(session).remove_visual(owner_id, dashboard_id, visual_id)
