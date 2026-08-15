"""La API, de extremo a extremo con el modelo guionado."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentcanvas.bootstrap.container import Container
from agentcanvas.infrastructure.web.app import create_app
from tests.fakes import FakeLLM, json_response

ENERO = b"fecha,Region,valor\n2026-01-15,Norte,100.0\n2026-01-20,Sur,150.0\n"
FEBRERO = b"fecha,Region,valor\n2026-02-10,Norte,120.0\n2026-02-11,Este,60.0\n"
SIN_VALOR = b"fecha,Region\n2026-03-01,Norte\n"

VENTAS_POR_REGION = {
    "type": "bar",
    "title": "Ventas por region",
    "x": {"field": "region"},
    "y": [{"field": "valor", "aggregation": "sum"}],
    "sort": {"by": "sum_valor", "direction": "desc"},
}
COLUMNA_INVENTADA = {
    "type": "bar",
    "title": "x",
    "x": {"field": "departamento"},
    "y": [{"field": "valor", "aggregation": "sum"}],
}


@pytest.fixture
async def client(container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _upload(client: AsyncClient, content: bytes, **data: str) -> dict[str, object]:
    response = await client.post(
        "/api/datasets",
        files={"file": ("ventas.csv", content, "text/csv")},
        data=data,
    )
    assert response.status_code == 201, response.text
    payload: dict[str, object] = response.json()
    return payload


# ------------------------------------------------------------------------ salud


async def test_health_reports_the_model_and_whether_the_key_is_set(
    client: AsyncClient,
) -> None:
    body = (await client.get("/health")).json()

    assert body["status"] == "ok"
    assert body["model"] == "gpt-5.6-luna"
    assert "llm_configured" in body


# --------------------------------------------------------------------- datasets


async def test_uploading_a_csv_creates_a_dataset_with_its_schema(
    client: AsyncClient,
) -> None:
    body = await _upload(client, ENERO)

    assert body["created_dataset"] is True
    dataset = body["dataset"]
    assert dataset["name"] == "ventas"  # type: ignore[index]
    assert [column["name"] for column in dataset["columns"]] == [  # type: ignore[index]
        "fecha",
        "region",
        "valor",
    ]
    assert body["preview"][0]["region"] == "Norte"  # type: ignore[index]


async def test_a_compatible_file_updates_the_dataset_instead_of_creating_one(
    client: AsyncClient,
) -> None:
    first = await _upload(client, ENERO)
    dataset_id = first["dataset"]["id"]  # type: ignore[index]

    second = await _upload(client, FEBRERO, dataset_id=dataset_id)

    assert second["created_dataset"] is False
    assert second["dataset"]["id"] == dataset_id  # type: ignore[index]
    assert second["dataset"]["row_count"] == 2  # type: ignore[index]


async def test_an_incompatible_file_is_rejected_naming_the_missing_column(
    client: AsyncClient,
) -> None:
    first = await _upload(client, ENERO)

    response = await client.post(
        "/api/datasets",
        files={"file": ("ventas.csv", SIN_VALOR, "text/csv")},
        data={"dataset_id": first["dataset"]["id"]},  # type: ignore[index]
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "SchemaMismatchError"
    assert body["problems"] == ["Falta la columna: valor"]


async def test_an_unsupported_extension_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/datasets",
        files={"file": ("informe.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert response.status_code == 415


async def test_datasets_can_be_listed_and_fetched(client: AsyncClient) -> None:
    created = await _upload(client, ENERO)
    dataset_id = created["dataset"]["id"]  # type: ignore[index]

    listed = (await client.get("/api/datasets")).json()
    fetched = (await client.get(f"/api/datasets/{dataset_id}")).json()

    assert [item["id"] for item in listed] == [dataset_id]
    assert fetched["id"] == dataset_id


async def test_an_unknown_dataset_is_a_404(client: AsyncClient) -> None:
    response = await client.get("/api/datasets/ds_inexistente")
    assert response.status_code == 404
    assert response.json()["error"] == "NotFoundError"


async def test_versions_accumulate(client: AsyncClient) -> None:
    first = await _upload(client, ENERO)
    dataset_id = first["dataset"]["id"]  # type: ignore[index]
    await _upload(client, FEBRERO, dataset_id=dataset_id)

    versions = (await client.get(f"/api/datasets/{dataset_id}/versions")).json()

    assert len(versions) == 2


# ---------------------------------------------------------------------- visuales


async def test_creating_a_visual_returns_the_spec_the_data_and_the_trace(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    llm.queue(json_response(VENTAS_POR_REGION))

    response = await client.post(
        f"/api/datasets/{created['dataset']['id']}/visuals",  # type: ignore[index]
        json={"instruction": "ventas por region"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spec"]["type"] == "bar"
    assert body["data"]["rows"] == [
        {"region": "Sur", "sum_valor": 150.0},
        {"region": "Norte", "sum_valor": 100.0},
    ]
    assert body["trace"]["attempts"] == 1


async def test_the_trace_exposes_what_the_model_got_wrong(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    llm.queue(json_response(COLUMNA_INVENTADA), json_response(VENTAS_POR_REGION))

    body = (
        await client.post(
            f"/api/datasets/{created['dataset']['id']}/visuals",  # type: ignore[index]
            json={"instruction": "ventas por departamento"},
        )
    ).json()

    # Un agente que se corrige en silencio es un agente que nadie puede mejorar.
    assert body["trace"]["repairs"] == 1
    assert any("departamento" in problem for problem in body["trace"]["problems"])


async def test_when_the_model_never_gets_it_right_the_answer_is_422(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    llm.queue(*[json_response(COLUMNA_INVENTADA) for _ in range(4)])

    response = await client.post(
        f"/api/datasets/{created['dataset']['id']}/visuals",  # type: ignore[index]
        json={"instruction": "algo imposible"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "AgentFailedError"


async def test_an_empty_instruction_is_rejected_before_reaching_the_model(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)

    response = await client.post(
        f"/api/datasets/{created['dataset']['id']}/visuals",  # type: ignore[index]
        json={"instruction": ""},
    )

    assert response.status_code == 422
    assert llm.calls == 0


# ----------------------------------------------------------------------- recalculo


async def test_a_saved_spec_recalculates_against_the_new_file_without_the_model(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    dataset_id = created["dataset"]["id"]  # type: ignore[index]
    llm.queue(json_response(VENTAS_POR_REGION))
    spec = (
        await client.post(
            f"/api/datasets/{dataset_id}/visuals", json={"instruction": "ventas por region"}
        )
    ).json()["spec"]

    await _upload(client, FEBRERO, dataset_id=dataset_id)
    recalculated = await client.post(f"/api/datasets/{dataset_id}/render", json={"spec": spec})

    assert recalculated.status_code == 200, recalculated.text
    assert recalculated.json()["data"]["rows"] == [
        {"region": "Norte", "sum_valor": 120.0},
        {"region": "Este", "sum_valor": 60.0},
    ]
    # El recalculo no vuelve a llamar al modelo: esa es toda la idea.
    assert llm.calls == 1


async def test_rendering_an_invalid_spec_says_which_column_is_wrong(
    client: AsyncClient,
) -> None:
    created = await _upload(client, ENERO)

    response = await client.post(
        f"/api/datasets/{created['dataset']['id']}/render",  # type: ignore[index]
        json={"spec": COLUMNA_INVENTADA},
    )

    assert response.status_code == 422
    assert any("departamento" in problem for problem in response.json()["problems"])


# ------------------------------------------------------------------------- stream


async def test_the_stream_emits_progress_and_then_the_result(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    llm.queue(json_response(COLUMNA_INVENTADA), json_response(VENTAS_POR_REGION))

    async with client.stream(
        "POST",
        f"/api/datasets/{created['dataset']['id']}/visuals/stream",  # type: ignore[index]
        json={"instruction": "ventas por region"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in response.aiter_text()])

    events = _parse_sse(body)
    kinds = [name for name, _ in events]
    assert kinds[-1] == "result"
    # El usuario ve que el agente se esta corrigiendo, no una rueda girando.
    assert any(payload.get("correcting") for name, payload in events if name == "step")
    assert events[-1][1]["data"]["rows"][0]["region"] == "Sur"


async def test_the_stream_reports_failure_as_an_event(
    client: AsyncClient, llm: FakeLLM
) -> None:
    created = await _upload(client, ENERO)
    llm.queue(*[json_response(COLUMNA_INVENTADA) for _ in range(4)])

    async with client.stream(
        "POST",
        f"/api/datasets/{created['dataset']['id']}/visuals/stream",  # type: ignore[index]
        json={"instruction": "imposible"},
    ) as response:
        body = "".join([chunk async for chunk in response.aiter_text()])

    name, payload = _parse_sse(body)[-1]
    # La cabecera ya se envio: un fallo tardio solo puede viajar como evento.
    assert name == "error"
    assert payload["error"] == "AgentFailedError"


def _parse_sse(body: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines and "data" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events
