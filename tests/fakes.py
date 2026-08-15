"""Dobles de prueba compartidos.

El `FakeLLM` es lo que permite testear el harness entero sin gastar un token ni
depender de la red: las respuestas van guionadas y las regresiones al tocar
prompts aparecen en CI, no en la factura.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agentcanvas.application.ports.llm import (
    LLMError,
    LLMRequest,
    LLMResponse,
    Usage,
)


class FakeLLM:
    """Implementa `LLMPort` devolviendo respuestas preparadas, en orden."""

    def __init__(self, responses: list[LLMResponse | Exception] | None = None) -> None:
        self._responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    def queue(self, *responses: LLMResponse | Exception) -> None:
        self._responses.extend(responses)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("El agente pidio mas respuestas de las preparadas")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    @property
    def calls(self) -> int:
        return len(self.requests)

    @property
    def exhausted(self) -> bool:
        return not self._responses


def json_response(payload: dict[str, Any], **usage: int) -> LLMResponse:
    """Lo que devuelve el adaptador cuando se pidio una salida estructurada."""
    return LLMResponse(
        content=json.dumps(payload, ensure_ascii=False),
        data=payload,
        usage=Usage(**usage) if usage else Usage(),
    )


def malformed_response(content: str = "no puedo hacer eso") -> LLMResponse:
    """El modelo no devolvio JSON utilizable: `data` viene vacio."""
    return LLMResponse(content=content, data=None)


def text_response(content: str) -> LLMResponse:
    return LLMResponse(content=content)


def unavailable(message: str = "boom") -> LLMError:
    from agentcanvas.application.ports.llm import LLMUnavailableError

    return LLMUnavailableError(message)


class StubCompletions:
    """Reemplaza `client.chat.completions` para testear el adaptador sin red."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.payloads: list[dict[str, Any]] = []

    async def create(self, **payload: Any) -> Any:
        self.payloads.append(payload)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class StubClient:
    def __init__(self, results: list[Any]) -> None:
        self.completions = StubCompletions(results)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def last_payload(self) -> dict[str, Any]:
        return self.completions.payloads[-1]


def completion(
    content: str | None = "",
    *,
    tool_calls: list[tuple[str, str, str]] | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> SimpleNamespace:
    """Construye algo con la forma de un `ChatCompletion` del SDK."""
    calls = [
        SimpleNamespace(
            id=call_id,
            type="function",
            function=SimpleNamespace(name=name, arguments=arguments),
        )
        for call_id, name, arguments in (tool_calls or [])
    ]
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=calls or None),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        ),
    )
