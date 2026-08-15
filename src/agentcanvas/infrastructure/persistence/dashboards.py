from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentcanvas.domain.shared.clock import utcnow
from agentcanvas.domain.visual.dashboard import Dashboard, Visual
from agentcanvas.infrastructure.persistence.models import DashboardRow, VisualRow
from agentcanvas.infrastructure.persistence.repositories import aware


class SqlAlchemyDashboardRepository:
    """Implementa `DashboardRepositoryPort`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, dashboard: Dashboard) -> None:
        self._session.add(
            DashboardRow(
                id=dashboard.id,
                owner_id=dashboard.owner_id,
                name=dashboard.name,
                created_at=dashboard.created_at,
                updated_at=dashboard.updated_at,
            )
        )
        await self._session.flush()

    async def get(self, dashboard_id: str) -> Dashboard | None:
        row = await self._session.get(DashboardRow, dashboard_id)
        return _to_dashboard(row) if row is not None else None

    async def list_for_owner(self, owner_id: str) -> list[Dashboard]:
        statement = (
            select(DashboardRow)
            .where(DashboardRow.owner_id == owner_id)
            .order_by(DashboardRow.updated_at.desc())
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_dashboard(row) for row in rows]

    async def rename(self, dashboard_id: str, name: str) -> None:
        row = await self._session.get(DashboardRow, dashboard_id)
        if row is None:
            raise LookupError(f"El dashboard {dashboard_id} no existe")
        row.name = name
        row.updated_at = utcnow()
        await self._session.flush()

    async def delete(self, dashboard_id: str) -> None:
        # SQLite no aplica ON DELETE CASCADE salvo que se active por conexion,
        # asi que los hijos se borran explicitamente.
        await self._session.execute(delete(VisualRow).where(VisualRow.dashboard_id == dashboard_id))
        await self._session.execute(delete(DashboardRow).where(DashboardRow.id == dashboard_id))
        await self._session.flush()

    async def add_visual(self, visual: Visual) -> None:
        self._session.add(
            VisualRow(
                id=visual.id,
                dashboard_id=visual.dashboard_id,
                dataset_id=visual.dataset_id,
                spec=visual.spec,
                placement=visual.placement,
                created_at=visual.created_at,
                updated_at=visual.updated_at,
            )
        )
        await self._touch(visual.dashboard_id)
        await self._session.flush()

    async def get_visual(self, visual_id: str) -> Visual | None:
        row = await self._session.get(VisualRow, visual_id)
        return _to_visual(row) if row is not None else None

    async def list_visuals(self, dashboard_id: str) -> list[Visual]:
        statement = (
            select(VisualRow)
            .where(VisualRow.dashboard_id == dashboard_id)
            .order_by(VisualRow.created_at)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_to_visual(row) for row in rows]

    async def update_visual(self, visual: Visual) -> None:
        row = await self._session.get(VisualRow, visual.id)
        if row is None:
            raise LookupError(f"El visual {visual.id} no existe")
        row.spec = visual.spec
        row.placement = visual.placement
        row.updated_at = visual.updated_at
        await self._touch(visual.dashboard_id)
        await self._session.flush()

    async def delete_visual(self, visual_id: str) -> None:
        row = await self._session.get(VisualRow, visual_id)
        if row is not None:
            await self._touch(row.dashboard_id)
            await self._session.delete(row)
            await self._session.flush()

    async def _touch(self, dashboard_id: str) -> None:
        """Tocar el dashboard al cambiar un visual mantiene util el orden por fecha."""
        row = await self._session.get(DashboardRow, dashboard_id)
        if row is not None:
            row.updated_at = utcnow()


def _to_dashboard(row: DashboardRow) -> Dashboard:
    return Dashboard(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )


def _to_visual(row: VisualRow) -> Visual:
    return Visual(
        id=row.id,
        dashboard_id=row.dashboard_id,
        dataset_id=row.dataset_id,
        spec=row.spec,
        placement=row.placement,
        created_at=aware(row.created_at),
        updated_at=aware(row.updated_at),
    )

