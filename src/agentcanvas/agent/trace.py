"""Traza de una ejecucion del agente.

Se guarda entera, incluidos los intentos fallidos. Cuando el usuario pregunte
"por que me ha salido este grafico" o cuando un prompt empiece a degradarse, la
traza es lo unico que permite responder sin adivinar.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.application.ports.llm import Usage
from agentcanvas.domain.shared.clock import utcnow


class StepKind(StrEnum):
    PROPOSAL = "proposal"
    """El modelo devolvio algo."""

    TOOL = "tool"
    """El agente esta usando una herramienta. `content` lo cuenta en palabras,
    para poder ensenarselo al usuario mientras espera."""

    REJECTED = "rejected"
    """Lo devuelto no paso la validacion; se le devolvieron los problemas."""

    ACCEPTED = "accepted"
    FAILED = "failed"


class AgentStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    iteration: int
    kind: StepKind
    content: str = ""
    problems: tuple[str, ...] = ()
    usage: Usage = Usage()
    at: datetime = Field(default_factory=utcnow)


class AgentTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps: tuple[AgentStep, ...] = ()
    usage: Usage = Usage()

    def with_step(self, step: AgentStep) -> AgentTrace:
        return AgentTrace(steps=(*self.steps, step), usage=self.usage + step.usage)

    @property
    def iterations(self) -> int:
        return len(self.steps)

    @property
    def repairs(self) -> int:
        """Cuantas veces hubo que corregir al modelo."""
        return sum(1 for step in self.steps if step.kind is StepKind.REJECTED)
