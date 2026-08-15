from __future__ import annotations

from enum import StrEnum

from openai import AsyncOpenAI

from agentcanvas.config import Settings
from agentcanvas.infrastructure.llm.capabilities import capabilities_for
from agentcanvas.infrastructure.llm.openai_compatible import OpenAICompatibleLLM


class ModelRole(StrEnum):
    """Para que se usa el modelo.

    Generar Python exige mas capacidad que producir la spec de un grafico, y
    cuesta mas. Separar los roles permite subir el esfuerzo solo donde importa
    sin encarecer todo lo demas.
    """

    GENERAL = "general"
    CODEGEN = "codegen"


def build_llm(settings: Settings, role: ModelRole = ModelRole.GENERAL) -> OpenAICompatibleLLM:
    model = settings.llm_model if role is ModelRole.GENERAL else settings.codegen_model
    effort = (
        settings.llm_reasoning_effort
        if role is ModelRole.GENERAL
        else settings.llm_codegen_reasoning_effort
    )
    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value() or "no-key",
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return OpenAICompatibleLLM(
        client=client,
        model=model,
        capabilities=capabilities_for(model),
        reasoning_effort=effort,
    )
