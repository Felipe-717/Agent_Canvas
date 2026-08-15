"""Puerto del modelo de lenguaje.

El resto del sistema conversa con el modelo unicamente a traves de estos tipos.
No aparece aqui nada que sea propio de un proveedor: ni `response_format`, ni
`reasoning_effort` en crudo, ni la forma de los tool calls de OpenAI. Esa
traduccion es trabajo del adaptador.

La consecuencia practica es que el harness y los casos de uso no saben si detras
hay la API de OpenAI o un modelo servido con vLLM.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.domain.shared.errors import DomainError


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    """Solo en mensajes del asistente."""

    tool_call_id: str | None = None
    """Solo en mensajes de rol `tool`: a que llamada responde."""

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: tuple[ToolCall, ...] = ()) -> Message:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> Message:
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id)


class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]
    """JSON Schema de los argumentos."""


class ResponseFormat(BaseModel):
    """Pide una respuesta que se ajuste a un JSON Schema."""

    model_config = ConfigDict(frozen=True)

    name: str
    schema_: dict[str, Any]


class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()
    response_format: ResponseFormat | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
        )


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = Usage()
    finish_reason: str | None = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMError(DomainError):
    """Fallo al hablar con el modelo. El harness decide si reintenta."""


class LLMUnavailableError(LLMError):
    """El proveedor no respondio: red, timeout, rate limit, 5xx."""


class LLMProtocolError(LLMError):
    """El modelo respondio algo que no encaja con lo que se le pidio.

    Tipicamente JSON invalido cuando se le exigio un schema. Es un fallo
    recuperable: el harness puede devolverselo y pedir correccion.
    """


class LLMPort(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
