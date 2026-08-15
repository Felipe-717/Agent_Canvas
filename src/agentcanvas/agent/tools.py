"""Herramientas que el agente puede usar.

Una herramienta es un nombre, una descripcion, un JSON Schema de argumentos y
una funcion. El modelo no ejecuta nada: pide, y el harness decide si esa
peticion es valida y la ejecuta. Esa asimetria es toda la seguridad del diseno.

El resultado que vuelve al modelo es siempre texto, incluso cuando la
herramienta produjo un objeto. Lo que el modelo necesita es leer; lo que el
programa necesita viaja aparte, en `payload`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentcanvas.application.ports.llm import ToolDefinition


class ToolOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    message: str
    """Lo que ve el modelo. Un error tambien es un resultado util: le dice que
    corregir sin abortar la conversacion."""

    payload: Any = None
    """Lo que se lleva quien invoco al agente. El modelo nunca lo ve."""

    done: bool = False
    """La herramienta ha cumplido el objetivo y el bucle puede terminar."""


ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolOutcome]]


class Tool(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    definition: ToolDefinition
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.definition.name


class Toolbox:
    """Las herramientas disponibles en una ejecucion."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    async def run(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            # Inventarse una herramienta es un error recuperable: se le dice
            # cuales existen y sigue trabajando.
            return ToolOutcome(
                message=(
                    f"No existe la herramienta '{name}'. "
                    f"Las disponibles son: {', '.join(self._tools)}"
                )
            )
        try:
            return await tool.handler(arguments)
        except Exception as error:
            # Un fallo de la herramienta no puede tumbar la conversacion: se le
            # cuenta al modelo, que suele saber reaccionar (otra hoja, otro rango).
            return ToolOutcome(message=f"La herramienta '{name}' fallo: {error}")


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: ToolHandler,
) -> Tool:
    return Tool(
        definition=ToolDefinition(name=name, description=description, parameters=parameters),
        handler=handler,
    )
