"""Adaptador unico para cualquier servidor compatible con la API de OpenAI.

La API oficial y un vLLM local son la misma clase con distinta configuracion:
lo que cambia es `base_url`, `model` y las capacidades declaradas del modelo.

Se usa `v1/chat/completions` y no la Responses API a proposito: es el endpoint
que ambos implementan de forma estable.
"""

from __future__ import annotations

from typing import Any

from openai import APIError, APITimeoutError, OpenAIError

from agentcanvas.application.ports.llm import (
    LLMProtocolError,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    Usage,
)
from agentcanvas.infrastructure.llm.capabilities import ModelCapabilities
from agentcanvas.infrastructure.llm.parsing import extract_json_object

_TOOL_PROTOCOL_INSTRUCTIONS = """\
Tienes estas herramientas disponibles:

{tools}

Para usar una, responde EXCLUSIVAMENTE con un objeto JSON de esta forma:

{{"tool": "nombre_de_la_herramienta", "arguments": {{...}}}}

Si ya puedes dar la respuesta final, responde con texto normal sin JSON."""

_SCHEMA_INSTRUCTIONS = """\
Responde EXCLUSIVAMENTE con un objeto JSON que cumpla este JSON Schema.
Sin explicaciones, sin texto antes o despues, sin vallas de codigo.

{schema}"""


class OpenAICompatibleLLM:
    """Implementa `LLMPort`."""

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        capabilities: ModelCapabilities,
        reasoning_effort: str | None = None,
    ) -> None:
        # `client` es un `AsyncOpenAI` (o cualquier cosa con la misma forma, que
        # es lo que permite testear el adaptador sin red).
        self._client = client
        self._model = model
        self._capabilities = capabilities
        self._reasoning_effort = reasoning_effort

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = self._build_payload(request)
        try:
            completion = await self._client.chat.completions.create(**payload)
        except APITimeoutError as error:
            raise LLMUnavailableError(f"El modelo no respondio a tiempo: {error}") from error
        except (APIError, OpenAIError) as error:
            raise LLMUnavailableError(f"Fallo al llamar al modelo: {error}") from error

        return self._parse(completion, request)

    # ---------------------------------------------------------------- peticion

    def _build_payload(self, request: LLMRequest) -> dict[str, Any]:
        messages = list(request.messages)
        payload: dict[str, Any] = {"model": self._model}

        if request.tools:
            if self._capabilities.supports_native_tools:
                payload["tools"] = [_as_openai_tool(tool) for tool in request.tools]
                payload["tool_choice"] = "auto"
            else:
                messages.insert(0, Message.system(_tool_prompt(request.tools)))

        if request.response_format is not None:
            if self._capabilities.supports_json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.response_format.name,
                        "schema": request.response_format.schema_,
                        # `strict` obligaria a que todo campo opcional fuese
                        # explicitamente nullable y requerido. Nuestras specs
                        # tienen muchos opcionales con valor por defecto, y la
                        # validacion de dominio ya es la barrera real.
                        "strict": False,
                    },
                }
            else:
                messages.append(
                    Message.system(
                        _SCHEMA_INSTRUCTIONS.format(schema=request.response_format.schema_)
                    )
                )

        payload["messages"] = [_as_openai_message(message) for message in messages]

        if self._reasoning_effort and self._capabilities.supports_reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        if request.temperature is not None and self._capabilities.supports_temperature:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_completion_tokens"] = request.max_output_tokens
        return payload

    # ---------------------------------------------------------------- respuesta

    def _parse(self, completion: Any, request: LLMRequest) -> LLMResponse:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise LLMProtocolError("El modelo devolvio una respuesta sin contenido")
        choice = choices[0]
        message = choice.message
        content = message.content or ""

        if self._capabilities.supports_native_tools:
            tool_calls = _native_tool_calls(message)
        else:
            tool_calls = _tool_calls_from_text(content, request.tools)
            if tool_calls:
                # El JSON era la llamada, no una respuesta para el usuario.
                content = ""

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=_usage_of(completion),
            finish_reason=getattr(choice, "finish_reason", None),
        )


def _as_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _as_openai_message(message: Message) -> dict[str, Any]:
    if message.role is Role.TOOL:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    payload: dict[str, Any] = {"role": str(message.role), "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": _dump(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return payload


def _dump(arguments: dict[str, Any]) -> str:
    import json

    return json.dumps(arguments, ensure_ascii=False)


def _tool_prompt(tools: tuple[ToolDefinition, ...]) -> str:
    described = "\n\n".join(
        f"- {tool.name}: {tool.description}\n  Argumentos: {tool.parameters}" for tool in tools
    )
    return _TOOL_PROTOCOL_INSTRUCTIONS.format(tools=described)


def _native_tool_calls(message: Any) -> tuple[ToolCall, ...]:
    raw_calls = getattr(message, "tool_calls", None) or ()
    calls: list[ToolCall] = []
    for call in raw_calls:
        arguments = call.function.arguments or "{}"
        try:
            parsed = extract_json_object(arguments) if arguments.strip() else {}
        except LLMProtocolError as error:
            raise LLMProtocolError(
                f"Argumentos invalidos en la llamada a '{call.function.name}': {error}"
            ) from error
        calls.append(ToolCall(id=call.id, name=call.function.name, arguments=parsed))
    return tuple(calls)


def _tool_calls_from_text(content: str, tools: tuple[ToolDefinition, ...]) -> tuple[ToolCall, ...]:
    """Protocolo de herramientas por texto, para modelos sin tool calling."""
    if not tools or "{" not in content:
        return ()
    try:
        payload = extract_json_object(content)
    except LLMProtocolError:
        # No todo JSON en la respuesta es una llamada: puede ser parte de la
        # respuesta final. Si no se parsea, se trata como texto.
        return ()
    name = payload.get("tool")
    if not isinstance(name, str) or name not in {tool.name for tool in tools}:
        return ()
    arguments = payload.get("arguments")
    return (
        ToolCall(
            id=f"call_{name}",
            name=name,
            arguments=arguments if isinstance(arguments, dict) else {},
        ),
    )


def _usage_of(completion: Any) -> Usage:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return Usage()
    details = getattr(usage, "prompt_tokens_details", None)
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cached_input_tokens=getattr(details, "cached_tokens", 0) or 0 if details else 0,
    )
