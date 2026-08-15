"""El bucle de herramientas y el agente que descifra un archivo.

Con el modelo guionado: lo que se comprueba no es que el modelo acierte, sino
que el harness le deje trabajar, le devuelva errores utiles y no le permita
saltarse la validacion.
"""

from __future__ import annotations

from typing import Any

from agentcanvas.agent.budget import Budget
from agentcanvas.agent.loop import AgentLoop
from agentcanvas.agent.tools import Toolbox, ToolOutcome, tool
from agentcanvas.application.ports.llm import Role
from tests.fakes import FakeLLM, text_response, tool_response

SCHEMA: dict[str, Any] = {"type": "object", "properties": {"x": {"type": "string"}}}


def _toolbox(outcomes: list[ToolOutcome]) -> tuple[Toolbox, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    async def handler(arguments: dict[str, Any]) -> ToolOutcome:
        seen.append(arguments)
        return outcomes.pop(0)

    return Toolbox([tool(name="mirar", description="d", parameters=SCHEMA, handler=handler)]), seen


# ------------------------------------------------------------------- toolbox


async def test_an_invented_tool_is_answered_with_the_real_ones() -> None:
    box, _ = _toolbox([])

    outcome = await box.run("borrar_todo", {})

    # Inventarse una herramienta es recuperable: se le dice cuales hay.
    assert "no existe" in outcome.message.lower()
    assert "mirar" in outcome.message
    assert not outcome.done


async def test_a_failing_tool_does_not_break_the_conversation() -> None:
    async def explode(_: dict[str, Any]) -> ToolOutcome:
        raise RuntimeError("la hoja no existe")

    box = Toolbox([tool(name="mirar", description="d", parameters=SCHEMA, handler=explode)])

    outcome = await box.run("mirar", {})

    assert "la hoja no existe" in outcome.message
    assert not outcome.done


# ---------------------------------------------------------------------- bucle


async def test_the_loop_feeds_the_tool_result_back_to_the_model() -> None:
    llm = FakeLLM([tool_response("mirar", {"x": "a"}), text_response("ya lo veo")])
    box, seen = _toolbox([ToolOutcome(message="fila 3: cabeceras")])

    result = await AgentLoop(llm).run([], box)

    assert seen == [{"x": "a"}]
    assert result.text == "ya lo veo"
    # El modelo tiene que haber visto el resultado en el segundo turno.
    tool_messages = [m for m in llm.requests[1].messages if m.role is Role.TOOL]
    assert tool_messages[0].content == "fila 3: cabeceras"


async def test_answering_in_text_is_a_legitimate_ending() -> None:
    # Un agente que explora un archivo caotico debe poder preguntar.
    llm = FakeLLM([text_response("¿Cual de las once hojas te interesa?")])

    result = await AgentLoop(llm).run([], Toolbox([]))

    assert not result.completed
    assert "once hojas" in result.text


async def test_a_terminal_tool_ends_the_loop_with_its_payload() -> None:
    llm = FakeLLM([tool_response("mirar", {})])
    box, _ = _toolbox([ToolOutcome(message="listo", payload={"filas": 85}, done=True)])

    result = await AgentLoop(llm).run([], box)

    assert result.completed
    assert result.payload == {"filas": 85}
    assert llm.exhausted


async def test_running_out_of_budget_still_produces_a_real_message() -> None:
    llm = FakeLLM(
        [
            tool_response("mirar", {}),
            tool_response("mirar", {}),
            text_response("He visto tres hojas con datos. ¿Cual quieres?"),
        ]
    )
    box, _ = _toolbox([ToolOutcome(message="a"), ToolOutcome(message="b")])

    result = await AgentLoop(llm, Budget(max_iterations=2)).run([], box)

    # El trabajo de exploracion ya esta pagado: se aprovecha en vez de soltar
    # un mensaje enlatado.
    assert "tres hojas" in result.text
    assert not result.completed


async def test_the_conversation_comes_back_so_it_can_be_continued() -> None:
    llm = FakeLLM([text_response("¿Que hoja?")])

    result = await AgentLoop(llm).run([], Toolbox([]))

    assert result.messages[-1].role is Role.ASSISTANT
    assert result.messages[-1].content == "¿Que hoja?"
