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

    activity: str = ""
    """Plantilla de lo que se le ensena al usuario mientras corre, con los
    argumentos entre llaves: "Mirando la hoja {hoja}". La escribe quien define
    la herramienta porque es quien sabe que esta pasando."""

    @property
    def name(self) -> str:
        return self.definition.name

    def describe(self, arguments: dict[str, Any]) -> str:
        if not self.activity:
            return ""
        try:
            return self.activity.format_map(_Missing(arguments))
        except Exception:
            return self.activity


class _Missing(dict[str, Any]):
    """Un argumento ausente no puede tumbar un mensaje de progreso."""

    def __missing__(self, key: str) -> str:
        return "…"


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

    def describe(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        return tool.describe(arguments) if tool else ""

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
    activity: str = "",
) -> Tool:
    return Tool(
        definition=ToolDefinition(name=name, description=description, parameters=parameters),
        handler=handler,
        activity=activity,
    )
