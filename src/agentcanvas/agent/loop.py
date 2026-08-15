"""Bucle del agente con herramientas.

El modelo mira, pide, lee lo que le devuelven, y vuelve a mirar. Termina de una
de tres formas: usando una herramienta terminal (ha conseguido lo que se le
pedia), respondiendo en texto (tiene una pregunta o una conclusion para el
usuario), o agotando el presupuesto.

Que responder en texto sea una salida legitima es deliberado. Un agente que
explora un archivo caotico a veces debe poder decir "he encontrado once hojas,
cual te interesa" en vez de adivinar.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentcanvas.agent.budget import Budget, BudgetExceededError, BudgetTracker
from agentcanvas.agent.structured import Observer
from agentcanvas.agent.tools import Toolbox
from agentcanvas.agent.trace import AgentStep, AgentTrace, StepKind
from agentcanvas.application.ports.llm import LLMPort, LLMRequest, Message

_WRAP_UP = """\
No puedes seguir explorando. Con lo que ya has visto, escribe al usuario un
mensaje breve: que has encontrado en el archivo y que necesitas saber para
continuar. Sin tecnicismos y sin llamar a ninguna herramienta."""


class LoopResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    payload: Any = None
    """Lo que devolvio la herramienta terminal, si la hubo."""

    text: str = ""
    """Lo que el agente le dice al usuario. Vacio si termino por herramienta."""

    messages: tuple[Message, ...] = ()
    """La conversacion completa, para poder continuarla en el siguiente turno."""

    trace: AgentTrace = AgentTrace()

    @property
    def completed(self) -> bool:
        """True si consiguio el objetivo; False si se quedo en una pregunta."""
        return self.payload is not None


class AgentLoop:
    def __init__(self, llm: LLMPort, budget: Budget | None = None) -> None:
        self._llm = llm
        self._budget = budget or Budget(max_iterations=12)

    async def run(
        self,
        messages: list[Message],
        toolbox: Toolbox,
        *,
        observer: Observer | None = None,
    ) -> LoopResult:
        tracker = BudgetTracker(self._budget)
        trace = AgentTrace()
        history = list(messages)

        def record(step: AgentStep) -> AgentTrace:
            if observer is not None:
                observer(step)
            return trace.with_step(step)

        while True:
            try:
                iteration = tracker.start_iteration()
            except BudgetExceededError as error:
                # Se le concede un turno final sin herramientas para que cuente
                # lo que ha averiguado. Un mensaje enlatado desperdiciaria todo
                # el trabajo de exploracion que ya esta pagado.
                closing = await self._llm.complete(
                    LLMRequest(messages=(*history, Message.user(_WRAP_UP)))
                )
                return LoopResult(
                    text=closing.content,
                    messages=(*history, Message.assistant(closing.content)),
                    trace=record(
                        AgentStep(
                            iteration=tracker.iterations,
                            kind=StepKind.FAILED,
                            content=closing.content,
                            problems=(str(error),),
                            usage=closing.usage,
                        )
                    ),
                )

            response = await self._llm.complete(
                LLMRequest(messages=tuple(history), tools=toolbox.definitions)
            )
            trace = record(
                AgentStep(
                    iteration=iteration,
                    kind=StepKind.PROPOSAL,
                    content=response.content,
                    usage=response.usage,
                )
            )
            # El gasto se acumula, pero pasarse no corta a mitad de turno: se
            # comprueba al pedir la siguiente iteracion, para no dejar una
            # llamada a herramienta sin su respuesta.
            with suppress(BudgetExceededError):
                tracker.record(response.usage)

            if not response.tool_calls:
                # Sin herramientas: el agente ha terminado de hablar consigo
                # mismo y se dirige al usuario.
                history.append(Message.assistant(response.content))
                return LoopResult(
                    text=response.content,
                    messages=tuple(history),
                    trace=record(AgentStep(iteration=iteration, kind=StepKind.ACCEPTED)),
                )

            history.append(Message.assistant(response.content, response.tool_calls))
            for call in response.tool_calls:
                # Se anuncia antes de ejecutar: leer un Excel grande tarda, y
                # el aviso llega tarde si se manda cuando ya termino.
                trace = record(
                    AgentStep(
                        iteration=iteration,
                        kind=StepKind.TOOL,
                        content=toolbox.describe(call.name, call.arguments),
                    )
                )
                outcome = await toolbox.run(call.name, call.arguments)
                history.append(Message.tool_result(call.id, outcome.message))
                if outcome.done:
                    return LoopResult(
                        payload=outcome.payload,
                        text=outcome.message,
                        messages=tuple(history),
                        trace=record(AgentStep(iteration=iteration, kind=StepKind.ACCEPTED)),
                    )
