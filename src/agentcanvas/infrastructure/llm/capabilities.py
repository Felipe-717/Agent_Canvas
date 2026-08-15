"""Que sabe hacer cada modelo.

Un servidor "compatible con OpenAI" no implementa lo mismo en todas partes. La
API oficial acepta `response_format` con JSON Schema estricto, tool calling
nativo y `reasoning_effort`; un vLLM recien levantado puede no aceptar ninguna
de las tres, o solo la primera bajo otro nombre.

En vez de que el adaptador vaya probando y fallando, cada modelo declara aqui
lo que soporta y el adaptador elige camino. Anadir un modelo open-source es
anadir una entrada a esta tabla, no tocar el harness.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    supports_json_schema: bool = True
    """`response_format` con JSON Schema. Si es falso, el schema se inyecta en
    el prompt y la respuesta se parsea a mano."""

    supports_native_tools: bool = True
    """Tool calling del proveedor. Si es falso, las herramientas se describen en
    el prompt y la eleccion se parsea de un bloque JSON."""

    supports_reasoning_effort: bool = False
    supports_temperature: bool = True


# La familia GPT-5.6 soporta todo, incluido `reasoning_effort`.
_GPT_5_6 = ModelCapabilities(
    supports_json_schema=True,
    supports_native_tools=True,
    supports_reasoning_effort=True,
    # Los modelos con razonamiento ignoran o rechazan `temperature`.
    supports_temperature=False,
)

# Suelo prudente para lo que no conocemos: se asume el minimo comun. Es
# preferible pasarse de conservador que fallar en la primera llamada contra un
# servidor recien levantado.
_UNKNOWN = ModelCapabilities(
    supports_json_schema=False,
    supports_native_tools=False,
    supports_reasoning_effort=False,
    supports_temperature=True,
)

_BY_PREFIX: tuple[tuple[str, ModelCapabilities], ...] = (
    ("gpt-5.6", _GPT_5_6),
    ("gpt-5", _GPT_5_6),
    (
        "gpt-4",
        ModelCapabilities(
            supports_json_schema=True,
            supports_native_tools=True,
            supports_reasoning_effort=False,
            supports_temperature=True,
        ),
    ),
    # vLLM sirve JSON Schema por guided decoding, que es su parte mas solida;
    # el tool calling nativo depende de que se arranque con un parser adecuado,
    # asi que no se da por hecho.
    (
        "vllm:",
        ModelCapabilities(
            supports_json_schema=True,
            supports_native_tools=False,
            supports_reasoning_effort=False,
            supports_temperature=True,
        ),
    ),
)


def capabilities_for(model: str) -> ModelCapabilities:
    normalized = model.strip().lower()
    for prefix, capabilities in _BY_PREFIX:
        if normalized.startswith(prefix):
            return capabilities
    return _UNKNOWN
