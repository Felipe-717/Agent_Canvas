"""El adaptador traduce en ambos sentidos y se adapta a lo que el modelo soporta.

Los dos caminos (capacidades plenas y modelo minimo) se testean en paralelo
porque el segundo es justamente el que solo se ejercitaria el dia de la
migracion a un modelo open-source, cuando ya seria tarde para descubrir que no
funciona.
"""

from __future__ import annotations

import json

import pytest
from openai import APITimeoutError

from agentcanvas.application.ports.llm import (
    LLMProtocolError,
    LLMRequest,
    LLMUnavailableError,
    Message,
    ResponseFormat,
    ToolCall,
    ToolDefinition,
)
from agentcanvas.infrastructure.llm.capabilities import ModelCapabilities, capabilities_for
from agentcanvas.infrastructure.llm.openai_compatible import OpenAICompatibleLLM
from tests.fakes import StubClient, completion

FULL = ModelCapabilities(
    supports_json_schema=True,
    supports_native_tools=True,
    supports_reasoning_effort=True,
    supports_temperature=False,
)
MINIMAL = ModelCapabilities(
    supports_json_schema=False,
    supports_native_tools=False,
    supports_reasoning_effort=False,
    supports_temperature=True,
)

TOOL = ToolDefinition(
    name="inspect_dataset",
    description="Devuelve el schema del dataset",
    parameters={"type": "object", "properties": {"dataset_id": {"type": "string"}}},
)
SCHEMA = ResponseFormat(name="visual_spec", schema_={"type": "object"})


def _llm(client: StubClient, capabilities: ModelCapabilities = FULL) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        client=client,
        model="gpt-5.6-luna",
        capabilities=capabilities,
        reasoning_effort="low",
    )


def _ask(content: str = "hola") -> LLMRequest:
    return LLMRequest(messages=(Message.user(content),))


async def test_a_plain_exchange_carries_content_and_usage() -> None:
    client = StubClient(
        [completion("Hola", prompt_tokens=10, completion_tokens=3, cached_tokens=8)]
    )

    response = await _llm(client).complete(_ask())

    assert response.content == "Hola"
    assert response.usage.input_tokens == 10
    assert response.usage.cached_input_tokens == 8
    assert response.usage.total_tokens == 13


async def test_the_model_and_reasoning_effort_travel_in_the_payload() -> None:
    client = StubClient([completion("ok")])

    await _llm(client).complete(_ask())

    assert client.last_payload["model"] == "gpt-5.6-luna"
    assert client.last_payload["reasoning_effort"] == "low"


async def test_temperature_is_omitted_for_a_reasoning_model() -> None:
    client = StubClient([completion("ok")])

    await _llm(client).complete(LLMRequest(messages=(Message.user("x"),), temperature=0.7))

    # Los modelos con razonamiento la rechazan: mandarla seria un error 400.
    assert "temperature" not in client.last_payload


async def test_temperature_travels_when_the_model_accepts_it() -> None:
    client = StubClient([completion("ok")])

    await _llm(client, MINIMAL).complete(
        LLMRequest(messages=(Message.user("x"),), temperature=0.7)
    )

    assert client.last_payload["temperature"] == 0.7


async def test_a_json_schema_becomes_response_format_when_supported() -> None:
    client = StubClient([completion('{"a": 1}')])

    await _llm(client).complete(LLMRequest(messages=(Message.user("x"),), response_format=SCHEMA))

    response_format = client.last_payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "visual_spec"


async def test_a_json_schema_becomes_a_prompt_when_unsupported() -> None:
    client = StubClient([completion('{"a": 1}')])

    await _llm(client, MINIMAL).complete(
        LLMRequest(messages=(Message.user("x"),), response_format=SCHEMA)
    )

    assert "response_format" not in client.last_payload
    # El schema tiene que llegar de alguna forma: si no por parametro, en texto.
    assert any("JSON Schema" in message["content"] for message in client.last_payload["messages"])


async def test_native_tool_calls_are_translated_into_domain_objects() -> None:
    client = StubClient(
        [completion(None, tool_calls=[("call_1", "inspect_dataset", '{"dataset_id": "ds_1"}')])]
    )

    response = await _llm(client).complete(
        LLMRequest(messages=(Message.user("x"),), tools=(TOOL,))
    )

    assert response.wants_tools
    assert response.tool_calls == (
        ToolCall(id="call_1", name="inspect_dataset", arguments={"dataset_id": "ds_1"}),
    )


async def test_tools_are_described_in_the_prompt_when_unsupported() -> None:
    client = StubClient(
        [completion('{"tool": "inspect_dataset", "arguments": {"dataset_id": "x"}}')]
    )

    response = await _llm(client, MINIMAL).complete(
        LLMRequest(messages=(Message.user("x"),), tools=(TOOL,))
    )

    assert "tools" not in client.last_payload
    assert client.last_payload["messages"][0]["role"] == "system"
    # El mismo resultado que con tool calling nativo, por otro camino.
    assert response.tool_calls[0].name == "inspect_dataset"
    assert response.tool_calls[0].arguments == {"dataset_id": "x"}
    assert response.content == ""


async def test_text_that_merely_contains_json_is_not_a_tool_call() -> None:
    client = StubClient([completion('El resultado es {"total": 42} segun los datos')])

    response = await _llm(client, MINIMAL).complete(
        LLMRequest(messages=(Message.user("x"),), tools=(TOOL,))
    )

    assert response.tool_calls == ()
    assert "42" in response.content


async def test_an_unknown_tool_name_is_not_taken_as_a_call() -> None:
    client = StubClient([completion('{"tool": "rm_rf", "arguments": {}}')])

    response = await _llm(client, MINIMAL).complete(
        LLMRequest(messages=(Message.user("x"),), tools=(TOOL,))
    )

    assert response.tool_calls == ()


async def test_a_conversation_with_tool_results_round_trips() -> None:
    client = StubClient([completion("listo")])
    call = ToolCall(id="call_1", name="inspect_dataset", arguments={"dataset_id": "ds_1"})

    await _llm(client).complete(
        LLMRequest(
            messages=(
                Message.user("x"),
                Message.assistant(tool_calls=(call,)),
                Message.tool_result("call_1", '{"columns": ["fecha"]}'),
            ),
            tools=(TOOL,),
        )
    )

    messages = client.last_payload["messages"]
    assert messages[1]["tool_calls"][0]["function"]["name"] == "inspect_dataset"
    assert json.loads(messages[1]["tool_calls"][0]["function"]["arguments"]) == call.arguments
    assert messages[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"columns": ["fecha"]}',
    }


async def test_broken_tool_arguments_are_a_protocol_error() -> None:
    client = StubClient([completion(None, tool_calls=[("c1", "inspect_dataset", "{no es json")])])

    with pytest.raises(LLMProtocolError):
        await _llm(client).complete(LLMRequest(messages=(Message.user("x"),), tools=(TOOL,)))


async def test_a_timeout_becomes_an_unavailable_error() -> None:
    client = StubClient([APITimeoutError(request=None)])  # type: ignore[arg-type]

    with pytest.raises(LLMUnavailableError):
        await _llm(client).complete(_ask())


async def test_an_empty_response_is_a_protocol_error() -> None:
    from types import SimpleNamespace

    client = StubClient([SimpleNamespace(choices=[], usage=None)])

    with pytest.raises(LLMProtocolError):
        await _llm(client).complete(_ask())


@pytest.mark.parametrize(
    ("model", "native_tools", "reasoning"),
    [
        ("gpt-5.6-luna", True, True),
        ("gpt-5.6-sol", True, True),
        ("gpt-4.1", True, False),
        ("Qwen/Qwen3-32B-Instruct", False, False),
    ],
)
def test_capabilities_are_resolved_per_model(
    model: str, native_tools: bool, reasoning: bool
) -> None:
    capabilities = capabilities_for(model)
    assert capabilities.supports_native_tools is native_tools
    assert capabilities.supports_reasoning_effort is reasoning


def test_an_unknown_model_gets_the_conservative_floor() -> None:
    # Mejor pasarse de prudente que fallar en la primera llamada contra un
    # servidor recien levantado.
    capabilities = capabilities_for("un-modelo-que-no-conocemos")
    assert not capabilities.supports_json_schema
    assert not capabilities.supports_native_tools
