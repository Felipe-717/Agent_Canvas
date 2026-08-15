"""Dashboards: guardar la logica, nunca los numeros."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentcanvas.bootstrap.container import Container
from agentcanvas.domain.visual.dashboard import GRID_COLUMNS, Placement
from agentcanvas.domain.visual.spec import Dimension
from agentcanvas.infrastructure.persistence.dashboards import SqlAlchemyDashboardRepository
from agentcanvas.infrastructure.web.app import create_app

ENERO = b"fecha,region,valor\n2026-01-15,Norte,100.0\n2026-01-20,Sur,150.0\n"
FEBRERO = b"fecha,region,valor\n2026-02-10,Norte,120.0\n2026-02-11,Este,60.0\n"

POR_REGION = {
    "type": "bar",
    "title": "Ventas por region",
    "x": {"field": "region"},
    "y": [{"field": "valor", "aggregation": "sum"}],
    "sort": {"by": "sum_valor", "direction": "desc"},
}
TOTAL = {
    "type": "kpi",
    "title": "Venta total",
    "y": [{"field": "valor", "aggregation": "sum"}],
}


@pytest.fixture
async def client(container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _dataset(client: AsyncClient, content: bytes = ENERO, **data: str) -> str:
    response = await client.post(
        "/api/datasets", files={"file": ("ventas.csv", content, "text/csv")}, data=data
    )
    assert response.status_code == 201, response.text
    dataset_id: str = response.json()["dataset"]["id"]
    return dataset_id


async def _dashboard(client: AsyncClient, name: str = "Ventas") -> str:
    response = await client.post("/api/dashboards", json={"name": name})
    assert response.status_code == 201, response.text
    dashboard_id: str = response.json()["id"]
    return dashboard_id


async def _add(client: AsyncClient, dashboard: str, dataset: str, spec: Any) -> dict[str, Any]:
    response = await client.post(
        f"/api/dashboards/{dashboard}/visuals", json={"dataset_id": dataset, "spec": spec}
    )
    assert response.status_code == 201, response.text
    payload: dict[str, Any] = response.json()
    return payload


# ------------------------------------------------------------------ dominio


def test_a_block_wider_than_the_grid_is_clamped() -> None:
    clamped = Placement(x=10, y=0, width=12, height=6).clamped()
    assert clamped.x == 0
    assert clamped.width == GRID_COLUMNS


def test_a_block_pushed_off_the_right_edge_comes_back() -> None:
    # Un visual fuera de la rejilla es un visual que el usuario no recupera.
    clamped = Placement(x=11, y=3, width=6, height=4).clamped()
    assert clamped.x == GRID_COLUMNS - 6
    assert clamped.y == 3


# --------------------------------------------------------------------- API


async def test_a_dashboard_starts_empty(client: AsyncClient) -> None:
    dashboard = await _dashboard(client)

    body = (await client.get(f"/api/dashboards/{dashboard}")).json()

    assert body["dashboard"]["name"] == "Ventas"
    assert body["visuals"] == []
    assert body["grid_columns"] == GRID_COLUMNS


async def test_visuals_stack_downwards_as_they_are_added(client: AsyncClient) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)

    first = await _add(client, dashboard, dataset, POR_REGION)
    second = await _add(client, dashboard, dataset, TOTAL)

    assert first["placement"]["y"] == 0
    # El usuario acaba de pedirlo: espera verlo aparecer, no encajado arriba.
    assert second["placement"]["y"] == first["placement"]["height"]


async def test_opening_a_dashboard_computes_the_numbers(client: AsyncClient) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    await _add(client, dashboard, dataset, POR_REGION)

    body = (await client.get(f"/api/dashboards/{dashboard}")).json()

    assert body["visuals"][0]["data"]["rows"] == [
        {"region": "Sur", "sum_valor": 150.0},
        {"region": "Norte", "sum_valor": 100.0},
    ]


async def test_the_whole_dashboard_updates_when_a_new_file_arrives(
    client: AsyncClient,
) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    await _add(client, dashboard, dataset, POR_REGION)
    await _add(client, dashboard, dataset, TOTAL)

    await _dataset(client, FEBRERO, dataset_id=dataset)
    body = (await client.get(f"/api/dashboards/{dashboard}")).json()

    # Esto es todo el producto en un assert: dos graficos guardados hace rato,
    # datos nuevos, cero llamadas al modelo.
    por_region, total = body["visuals"]
    assert por_region["data"]["rows"] == [
        {"region": "Norte", "sum_valor": 120.0},
        {"region": "Este", "sum_valor": 60.0},
    ]
    assert total["data"]["rows"] == [{"sum_valor": 180.0}]


async def test_the_layout_survives_a_reload(client: AsyncClient) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    visual = await _add(client, dashboard, dataset, POR_REGION)

    saved = await client.put(
        f"/api/dashboards/{dashboard}/layout",
        json={
            "items": [
                {
                    "visual_id": visual["id"],
                    "placement": {"x": 6, "y": 2, "width": 6, "height": 8},
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text

    reopened = (await client.get(f"/api/dashboards/{dashboard}")).json()
    assert reopened["visuals"][0]["placement"] == {"x": 6, "y": 2, "width": 6, "height": 8}


async def test_an_impossible_placement_is_corrected_instead_of_rejected(
    client: AsyncClient,
) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    visual = await _add(client, dashboard, dataset, POR_REGION)

    await client.put(
        f"/api/dashboards/{dashboard}/layout",
        json={
            "items": [
                {
                    "visual_id": visual["id"],
                    "placement": {"x": 11, "y": 0, "width": 6, "height": 6},
                }
            ]
        },
    )

    reopened = (await client.get(f"/api/dashboards/{dashboard}")).json()
    assert reopened["visuals"][0]["placement"]["x"] == 6


async def test_a_broken_visual_does_not_take_down_the_dashboard(
    client: AsyncClient, container: Container
) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    await _add(client, dashboard, dataset, POR_REGION)
    roto = await _add(
        client,
        dashboard,
        dataset,
        {
            "type": "bar",
            "title": "Roto",
            "x": {"field": "region"},
            "y": [{"field": "valor", "aggregation": "sum"}],
        },
    )
    # Se corrompe la spec guardada por detras, como si el dataset hubiera
    # cambiado bajo los pies del visual.
    session = container.session_factory()
    try:
        repository = SqlAlchemyDashboardRepository(session)
        stored = await repository.get_visual(roto["id"])
        assert stored is not None
        await repository.update_visual(
            stored.with_spec(stored.spec.model_copy(update={"x": Dimension(field="fantasma")}))
        )
        await session.commit()
    finally:
        await session.close()

    body = (await client.get(f"/api/dashboards/{dashboard}")).json()

    bueno, malo = body["visuals"]
    assert bueno["data"] is not None
    assert malo["data"] is None
    # Un dashboard a medias es infinitamente mejor que una pantalla de error.
    assert "fantasma" in malo["error"]


async def test_deleting_a_visual_leaves_the_rest(client: AsyncClient) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    first = await _add(client, dashboard, dataset, POR_REGION)
    await _add(client, dashboard, dataset, TOTAL)

    response = await client.delete(f"/api/dashboards/{dashboard}/visuals/{first['id']}")

    assert response.status_code == 204
    body = (await client.get(f"/api/dashboards/{dashboard}")).json()
    assert [visual["spec"]["title"] for visual in body["visuals"]] == ["Venta total"]


async def test_deleting_a_dashboard_takes_its_visuals_with_it(
    client: AsyncClient, container: Container
) -> None:
    dashboard = await _dashboard(client)
    dataset = await _dataset(client)
    await _add(client, dashboard, dataset, POR_REGION)

    assert (await client.delete(f"/api/dashboards/{dashboard}")).status_code == 204

    assert (await client.get(f"/api/dashboards/{dashboard}")).status_code == 404
    session = container.session_factory()
    try:
        assert await SqlAlchemyDashboardRepository(session).list_visuals(dashboard) == []
    finally:
        await session.close()


async def test_dashboards_can_be_listed_and_renamed(client: AsyncClient) -> None:
    dashboard = await _dashboard(client, "Borrador")

    renamed = await client.patch(f"/api/dashboards/{dashboard}", json={"name": "Ventas 2026"})

    assert renamed.json()["name"] == "Ventas 2026"
    listed = (await client.get("/api/dashboards")).json()
    assert [item["name"] for item in listed] == ["Ventas 2026"]


async def test_adding_a_visual_from_an_unknown_dataset_is_a_404(
    client: AsyncClient,
) -> None:
    dashboard = await _dashboard(client)

    response = await client.post(
        f"/api/dashboards/{dashboard}/visuals",
        json={"dataset_id": "ds_inexistente", "spec": POR_REGION},
    )

    assert response.status_code == 404
