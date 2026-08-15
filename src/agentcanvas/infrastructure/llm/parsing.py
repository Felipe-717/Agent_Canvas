"""Extraccion de JSON de una respuesta en texto.

Necesario para los modelos que no soportan salidas estructuradas nativas: se
les pide JSON y devuelven JSON envuelto en explicaciones, en vallas de codigo,
o ambas cosas. Rechazar esas respuestas seria tirar trabajo util.
"""

from __future__ import annotations

import json
from typing import Any

from agentcanvas.application.ports.llm import LLMProtocolError


def extract_json_object(text: str) -> dict[str, Any]:
    """Devuelve el primer objeto JSON completo del texto."""
    candidate = _strip_code_fence(text.strip())
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = _first_balanced_object(candidate)
    if not isinstance(parsed, dict):
        raise LLMProtocolError(f"Se esperaba un objeto JSON y llego: {text[:200]}")
    return parsed


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    without_open = text.split("\n", 1)[1] if "\n" in text else ""
    closing = without_open.rfind("```")
    return without_open[:closing].strip() if closing != -1 else without_open.strip()


def _first_balanced_object(text: str) -> Any:
    """Recorre el texto contando llaves, respetando las que van entre comillas."""
    start = text.find("{")
    if start == -1:
        raise LLMProtocolError(f"La respuesta no contiene JSON: {text[:200]}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError as error:
                    raise LLMProtocolError(f"JSON invalido en la respuesta: {error}") from error
    raise LLMProtocolError(f"La respuesta contiene un JSON sin cerrar: {text[:200]}")
