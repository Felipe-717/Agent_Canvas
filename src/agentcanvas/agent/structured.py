"""Generacion estructurada con ciclo de correccion.

El nucleo del harness: se le pide al modelo un objeto que cumpla un modelo
pydantic, se valida contra el dominio, y si falla se le devuelven los problemas
para que lo intente de nuevo. Ni un `eval`, ni un parser a medida por cada caso,
ni un framework de terceros decidiendo por nosotros.

Que el modelo se equivoque es normal y esta contemplado. Lo que no puede pasar
es que un error suyo llegue a los datos: cada intento pasa por la validacion del
dominio antes de darse por bueno.

Este modulo no importa infraestructura. Habla con el modelo por `LLMPort` y
recibe el JSON ya parseado, asi que no sabe ni le importa si detras hubo salidas
estructuradas nativas o un prompt pidiendo JSON a un modelo mas simple.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agentcanvas.agent.budget import Budget, BudgetExceededError, BudgetTracker
from agentcanvas.agent.trace import AgentStep, AgentTrace, StepKind
from agentcanvas.application.ports.llm import (
    LLMPort,
    LLMRequest,
    Message,
    ResponseFormat,
)
from agentcanvas.domain.shared.errors import DomainError

Validator = Callable[[Any], tuple[str, ...]]
"""Comprueba el objeto ya tipado contra el dominio. Vacio = correcto."""

Observer = Callable[[AgentStep], None]
"""Se le notifica cada paso segun ocurre.

Existe para poder retransmitir el progreso al usuario mientras el agente
trabaja. Es sincrono y no devuelve nada a proposito: un observador no puede
influir en la ejecucion, solo mirarla."""

_NO_JSON = "No has devuelto un objeto JSON. Responde solo con el JSON, sin texto alrededor."

_REPAIR_PROMPT = """\
Lo que has propuesto no es valido:

{problems}

Corrigelo y responde de nuevo con el objeto JSON completo."""


class AgentFailedError(DomainError):
    """El modelo no consiguio producir algo valido dentro del presupuesto."""

    def __init__(self, problems: tuple[str, ...], trace: AgentTrace) -> None:
        detail = "\n- ".join(problems) if problems else "sin detalle"
        super().__init__(f"El agente no pudo completar la tarea:\n- {detail}")
        self.problems = problems
        self.trace = trace


class StructuredResult[T: BaseModel](BaseModel):
    model_config = ConfigDict(frozen=True)

    value: T
    trace: AgentTrace


class StructuredGenerator:
    """Pide al modelo un objeto tipado y lo corrige hasta que sea valido."""

    def __init__(self, llm: LLMPort, budget: Budget | None = None) -> None:
        self._llm = llm
        self._budget = budget or Budget()

    async def generate[T: BaseModel](
        self,
        *,
        output: type[T],
        name: str,
        system: str,
        user: str,
        validate: Validator | None = None,
        observer: Observer | None = None,
    ) -> StructuredResult[T]:
        tracker = BudgetTracker(self._budget)
        trace = AgentTrace()

        def record(step: AgentStep) -> AgentTrace:
            if observer is not None:
                observer(step)
            return trace.with_step(step)

        messages: list[Message] = [Message.system(system), Message.user(user)]
        response_format = ResponseFormat(name=name, schema_=output.model_json_schema())
        problems: tuple[str, ...] = ()

        while True:
            try:
                iteration = tracker.start_iteration()
            except BudgetExceededError as error:
                raise AgentFailedError(problems or (str(error),), trace) from error

            response = await self._llm.complete(
                LLMRequest(messages=tuple(messages), response_format=response_format)
            )
            trace = record(
                AgentStep(
                    iteration=iteration,
                    kind=StepKind.PROPOSAL,
                    content=response.content,
                    usage=response.usage,
                )
            )
            try:
                # El gasto se contabiliza despues de anotarlo en la traza: si el
                # presupuesto salta aqui, la traza ya refleja lo que se consumio.
                tracker.record(response.usage)
            except BudgetExceededError as error:
                raise AgentFailedError((str(error),), trace) from error

            value, problems = _interpret(response.data, output, validate)
            if value is not None:
                return StructuredResult[T](
                    value=value,
                    trace=record(AgentStep(iteration=iteration, kind=StepKind.ACCEPTED)),
                )

            trace = record(
                AgentStep(iteration=iteration, kind=StepKind.REJECTED, problems=problems)
            )
            if not tracker.has_iterations_left:
                raise AgentFailedError(
                    problems,
                    record(
                        AgentStep(iteration=iteration, kind=StepKind.FAILED, problems=problems)
                    ),
                )

            messages.append(Message.assistant(response.content))
            messages.append(Message.user(_REPAIR_PROMPT.format(problems="\n".join(problems))))


def _interpret[T: BaseModel](
    data: dict[str, Any] | None, output: type[T], validate: Validator | None
) -> tuple[T | None, tuple[str, ...]]:
    """Convierte lo devuelto en objeto de dominio o en una lista de problemas."""
    if data is None:
        return None, (_NO_JSON,)

    try:
        value = output.model_validate(data)
    except ValidationError as error:
        return None, _readable(error)

    problems = validate(value) if validate is not None else ()
    return (None, problems) if problems else (value, ())


def _readable(error: ValidationError) -> tuple[str, ...]:
    """Errores de pydantic en una forma que el modelo pueda accionar."""
    return tuple(
        f"El campo '{'.'.join(str(part) for part in issue['loc'])}': {issue['msg']}"
        for issue in error.errors()
    )
