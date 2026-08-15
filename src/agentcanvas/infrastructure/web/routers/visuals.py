from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agentcanvas.agent.trace import AgentStep, StepKind
from agentcanvas.application.use_cases.create_visual import CreateVisualCommand
from agentcanvas.application.use_cases.render_visual import RenderVisualCommand
from agentcanvas.domain.shared.errors import DomainError
from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep
from agentcanvas.infrastructure.web.errors import as_payload
from agentcanvas.infrastructure.web.schemas import (
    CreateVisualIn,
    RenderVisualIn,
    TraceOut,
    VisualOut,
)

router = APIRouter(prefix="/api/datasets/{dataset_id}", tags=["visuals"])


@router.post("/visuals", response_model=VisualOut)
async def create_visual(
    dataset_id: str,
    body: CreateVisualIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> VisualOut:
    """Crea una visualizacion a partir de una peticion en lenguaje natural."""
    result = await container.create_visual(session).execute(
        CreateVisualCommand(
            owner_id=owner_id, dataset_id=dataset_id, instruction=body.instruction
        )
    )
    return VisualOut(spec=result.spec, data=result.data, trace=TraceOut.of(result.trace))


@router.post("/render", response_model=VisualOut)
async def render_visual(
    dataset_id: str,
    body: RenderVisualIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> VisualOut:
    """Ejecuta una spec ya guardada contra la version activa del dataset.

    Es el camino del recalculo: no interviene el modelo, no cuesta nada y da
    siempre el mismo resultado para los mismos datos.
    """
    data = await container.render_visual(session).execute(
        RenderVisualCommand(owner_id=owner_id, dataset_id=dataset_id, spec=body.spec)
    )
    return VisualOut(spec=body.spec, data=data)


@router.post("/visuals/stream")
async def create_visual_stream(
    dataset_id: str,
    body: CreateVisualIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> StreamingResponse:
    """Lo mismo, retransmitiendo el progreso del agente por SSE.

    Importa porque un intento fallido puede tardar varios segundos y el usuario
    merece ver que el agente esta corrigiendose, no una rueda girando.
    """
    return StreamingResponse(
        _stream(dataset_id, body, container, session, owner_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream(
    dataset_id: str,
    body: CreateVisualIn,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> AsyncIterator[str]:
    events: asyncio.Queue[AgentStep | None] = asyncio.Queue()

    task = asyncio.create_task(
        container.create_visual(session).execute(
            CreateVisualCommand(
                owner_id=owner_id, dataset_id=dataset_id, instruction=body.instruction
            ),
            observer=events.put_nowait,
        )
    )
    task.add_done_callback(lambda _: events.put_nowait(None))

    while True:
        step = await events.get()
        if step is None:
            break
        yield _event("step", _step_payload(step))

    try:
        result = task.result()
    except DomainError as error:
        yield _event("error", as_payload(error).model_dump())
        return
    yield _event(
        "result",
        VisualOut(
            spec=result.spec, data=result.data, trace=TraceOut.of(result.trace)
        ).model_dump(mode="json"),
    )


def _step_payload(step: AgentStep) -> dict[str, object]:
    return {
        "iteration": step.iteration,
        "kind": str(step.kind),
        "problems": list(step.problems),
        # El contenido crudo del modelo no se retransmite: puede ser largo y no
        # le dice nada al usuario. Lo que le importa es si va bien o se corrige.
        "correcting": step.kind is StepKind.REJECTED,
    }


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
