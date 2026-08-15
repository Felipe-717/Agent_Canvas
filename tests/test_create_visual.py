"""De una frase a un grafico, con el modelo guionado.

Verifica lo que el sistema promete: el usuario escribe en lenguaje natural y
obtiene numeros correctos, y si el modelo se equivoca se corrige solo con los
mensajes de validacion del dominio en vez de romper nada.
"""

from __future__ import annotations

import pytest

from agentcanvas.agent.structured import AgentFailedError
from agentcanvas.agent.visual_agent import SYSTEM_PROMPT, describe_columns
from agentcanvas.application.use_cases.create_visual import (
    CreateVisualCommand,
    CreateVisualResult,
)
from agentcanvas.application.use_cases.ingest_file import IngestFileCommand, IngestFileResult
from agentcanvas.application.use_cases.render_visual import RenderVisualCommand
from agentcanvas.bootstrap.container import Container
from agentcanvas.domain.dataset.schema import ColumnSchema, ColumnType, DatasetSchema
from agentcanvas.domain.visual.spec import ChartType
from tests.conftest import OWNER
from tests.fakes import FakeLLM, json_response

VENTAS = (
    "fecha,Región,valor\n"
    "2026-01-15,Norte,100.0\n"
    "2026-01-20,Sur,150.0\n"
    "2026-02-10,Norte,120.0\n"
    "2026-02-11,Sur,90.0\n"
).encode()

VENTAS_MENSUALES = {
    "type": "line",
    "title": "Ventas mensuales",
    "x": {"field": "fecha", "time_grain": "month"},
    "y": [{"field": "valor", "aggregation": "sum"}],
}

COLUMNA_INVENTADA = {
    "type": "bar",
    "title": "Ventas por departamento",
    "x": {"field": "departamento"},
    "y": [{"field": "valor", "aggregation": "sum"}],
}


async def _ingest(container: Container) -> IngestFileResult:
    session = container.session_factory()
    try:
        return await container.ingest_file(session).execute(
            IngestFileCommand(owner_id=OWNER, filename="ventas.csv", content=VENTAS)
        )
    finally:
        await session.close()


async def _create(container: Container, dataset_id: str, instruction: str) -> CreateVisualResult:
    session = container.session_factory()
    try:
        return await container.create_visual(session).execute(
            CreateVisualCommand(
                owner_id=OWNER, dataset_id=dataset_id, instruction=instruction
            )
        )
    finally:
        await session.close()


async def test_a_natural_language_request_becomes_a_chart(
    container: Container, llm: FakeLLM
) -> None:
    dataset = await _ingest(container)
    llm.queue(json_response(VENTAS_MENSUALES))

    result = await _create(container, dataset.dataset.id, "ventas mensuales")

    assert result.spec.type is ChartType.LINE
    assert [row["sum_valor"] for row in result.data.rows] == [250.0, 210.0]


async def test_the_prompt_carries_the_schema_and_real_rows(
    container: Container, llm: FakeLLM
) -> None:
    dataset = await _ingest(container)
    llm.queue(json_response(VENTAS_MENSUALES))

    await _create(container, dataset.dataset.id, "ventas mensuales")

    prompt = llm.requests[0].messages[1].content
    assert "fecha (date)" in prompt
    # El nombre original importa: el usuario escribira "Región", no "region".
    assert 'en el archivo: "Región"' in prompt
    # Ver datos reales cambia que visualizacion tiene sentido proponer.
    assert "Norte" in prompt


async def test_an_invented_column_is_corrected_without_reaching_the_data(
    container: Container, llm: FakeLLM
) -> None:
    dataset = await _ingest(container)
    llm.queue(json_response(COLUMNA_INVENTADA), json_response(VENTAS_MENSUALES))

    result = await _create(container, dataset.dataset.id, "ventas por departamento")

    assert llm.calls == 2
    assert result.trace.repairs == 1
    # El mensaje que recibio el modelo le dice que columnas si existen.
    correction = llm.requests[1].messages[-1].content
    assert "departamento" in correction
    assert "region" in correction


async def test_it_gives_up_cleanly_when_the_model_insists_on_being_wrong(
    container: Container, llm: FakeLLM
) -> None:
    dataset = await _ingest(container)
    llm.queue(*[json_response(COLUMNA_INVENTADA) for _ in range(4)])

    with pytest.raises(AgentFailedError) as error:
        await _create(container, dataset.dataset.id, "algo imposible")

    # Se agota el presupuesto configurado, no se llama al modelo indefinidamente.
    assert llm.calls == container.settings.agent_max_repair_attempts + 1
    assert any("departamento" in problem for problem in error.value.problems)


async def test_the_returned_spec_is_what_gets_saved(container: Container, llm: FakeLLM) -> None:
    dataset = await _ingest(container)
    llm.queue(json_response(VENTAS_MENSUALES))

    result = await _create(container, dataset.dataset.id, "ventas mensuales")

    # Guardar la spec y no los datos es lo que permite recalcularla despues:
    # volver a ejecutarla, sin modelo de por medio, da exactamente lo mismo.
    session = container.session_factory()
    try:
        rendered = await container.render_visual(session).execute(
            RenderVisualCommand(
                owner_id=OWNER, dataset_id=dataset.dataset.id, spec=result.spec
            )
        )
    finally:
        await session.close()

    assert rendered == result.data
    assert llm.calls == 1


def test_the_column_description_is_readable_for_the_model() -> None:
    schema = DatasetSchema(
        columns=(
            ColumnSchema.create("Fecha de Emisión", ColumnType.DATE),
            ColumnSchema.create("valor", ColumnType.FLOAT),
        )
    )

    described = describe_columns(schema)

    assert "- fecha_de_emision (date)" in described
    assert 'en el archivo: "Fecha de Emisión"' in described
    # Una columna que no cambia de nombre no necesita la coletilla.
    assert "- valor (float)\n" in described + "\n"


def test_the_system_prompt_states_the_rules_that_the_validation_enforces() -> None:
    # Si el prompt y la validacion se desincronizan, el agente entra en bucles
    # de correccion por reglas que nadie le conto.
    assert "time_grain" in SYSTEM_PROMPT
    assert "count" in SYSTEM_PROMPT
    assert "group_by" in SYSTEM_PROMPT
