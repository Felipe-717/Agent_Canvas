"""Presupuesto de una ejecucion del agente.

Un agente sin limite explicito es una factura sin limite explicito. Cada
ejecucion declara cuantas iteraciones y cuantos tokens puede gastar, y el
harness corta en cuanto se pasa, con un error que dice exactamente que limite
se alcanzo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.application.ports.llm import Usage
from agentcanvas.domain.shared.errors import DomainError


class BudgetExceededError(DomainError):
    def __init__(self, limit: str, spent: int, allowed: int) -> None:
        super().__init__(f"Se agoto el presupuesto del agente: {limit} ({spent} de {allowed})")
        self.limit = limit
        self.spent = spent
        self.allowed = allowed


class Budget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_iterations: int = Field(default=8, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    """Suma de entrada y salida. `None` deja el limite solo en iteraciones."""


class BudgetTracker:
    """Estado vivo del presupuesto durante una ejecucion."""

    def __init__(self, budget: Budget) -> None:
        self._budget = budget
        self._iterations = 0
        self._usage = Usage()

    @property
    def iterations(self) -> int:
        return self._iterations

    @property
    def usage(self) -> Usage:
        return self._usage

    def start_iteration(self) -> int:
        """Reserva una iteracion. Devuelve su indice, empezando en 1."""
        if self._iterations >= self._budget.max_iterations:
            raise BudgetExceededError(
                "iteraciones", self._iterations, self._budget.max_iterations
            )
        self._iterations += 1
        return self._iterations

    def record(self, usage: Usage) -> None:
        self._usage = self._usage + usage
        allowed = self._budget.max_tokens
        if allowed is not None and self._usage.total_tokens > allowed:
            raise BudgetExceededError("tokens", self._usage.total_tokens, allowed)

    @property
    def has_iterations_left(self) -> bool:
        return self._iterations < self._budget.max_iterations
