from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agentcanvas.agent.trace import AgentStep, StepKind
from agentcanvas.application.use_cases.chat import RenderedMessage
from agentcanvas.domain.chat.entities import (
    ChatMessage,
    Conversation,
    DatasetArtifact,
    VisualArtifact,
)
from agentcanvas.domain.shared.errors import DomainError
from agentcanvas.domain.visual.explain import as_python
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep
from agentcanvas.infrastructure.web.errors import as_payload
from agentcanvas.infrastructure.web.schemas import TraceOut

router = APIRouter(prefix="/api/conversations", tags=["chat"])

MAX_UPLOAD_BYTES = 40 * 1024 * 1024


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, conversation: Conversation) -> ConversationOut:
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class AttachmentOut(BaseModel):
    file_id: str
    filename: str


class ArtifactOut(BaseModel):
    """Un artefacto listo para pintar.

    Los datos del grafico viajan aqui, pero no estan guardados en ninguna
    parte: se acaban de calcular al cargar la conversacion.
    """

    kind: str
    dataset_id: str
    name: str | None = None
    row_count: int | None = None
    columns: list[str] | None = None
    origin: str | None = None
    warnings: list[str] = []
    """Lo que olio raro al extraer. Se ensena al usuario, no solo al modelo."""

    preview: list[dict[str, Any]] = []
    """Primeras filas, recalculadas al abrir. Sin ellas una extraccion
    equivocada no se nota hasta que un grafico sale mal."""
    spec: VisualSpec | None = None
    data: VisualData | None = None
    code: str | None = None
    """El calculo exacto en Python. Se genera de la spec y hay un test que lo
    ejecuta y compara con el motor, asi que no puede mentir."""

    error: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    text: str
    attachments: list[AttachmentOut]
    artifacts: list[ArtifactOut]
    created_at: datetime

    @classmethod
    def of(cls, rendered: RenderedMessage) -> MessageOut:
        message = rendered.message
        return cls(
            id=message.id,
            role=str(message.role),
            text=message.text,
            attachments=[
                AttachmentOut(file_id=a.file_id, filename=a.filename)
                for a in message.attachments
            ],
            artifacts=[
                _artifact(
                    artifact,
                    rendered.data.get(str(index)),
                    rendered.previews.get(str(index), ()),
                    rendered.errors.get(str(index)),
                )
                for index, artifact in enumerate(message.artifacts)
            ],
            created_at=message.created_at,
        )

    @classmethod
    def plain(cls, message: ChatMessage) -> MessageOut:
        return cls.of(RenderedMessage(message=message))


class TurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    trace: TraceOut


class SendIn(BaseModel):
    text: str = ""


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def start(
    container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> ConversationOut:
    return ConversationOut.of(await container.chat(session).start(owner_id))


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> list[ConversationOut]:
    conversations = await container.chat(session).list_conversations(owner_id)
    return [ConversationOut.of(conversation) for conversation in conversations]


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def history(
    conversation_id: str, container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> list[MessageOut]:
    """La conversacion con sus graficos recalculados contra los datos de hoy."""
    rendered = await container.chat(session).history(owner_id, conversation_id)
    return [MessageOut.of(message) for message in rendered]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    conversation_id: str, container: ContainerDep, session: SessionDep, owner_id: OwnerDep
) -> None:
    await container.chat(session).delete(owner_id, conversation_id)


@router.post("/{conversation_id}/messages", response_model=TurnOut)
async def send(
    conversation_id: str,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
    text: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> TurnOut:
    """Envia un mensaje, opcionalmente con un archivo adjunto.

    Es multipart y no JSON porque el adjunto viaja en el mismo turno que el
    texto: separarlos obligaria al usuario a subir y luego escribir, que no es
    como funciona un chat.
    """
    upload = await _read_upload(file)
    turn = await container.chat(session).send(
        owner_id, conversation_id, text=text, upload=upload
    )
    rendered = await container.chat(session).history(owner_id, conversation_id)
    by_id = {item.message.id: item for item in rendered}

    return TurnOut(
        user_message=MessageOut.plain(turn.user_message),
        assistant_message=MessageOut.of(
            by_id.get(turn.assistant_message.id)
            or RenderedMessage(message=turn.assistant_message)
        ),
        trace=TraceOut.of(turn.trace),
    )


@router.post("/{conversation_id}/messages/stream")
async def send_streaming(
    conversation_id: str,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
    text: Annotated[str, Form()] = "",
    file: Annotated[UploadFile | None, File()] = None,
) -> StreamingResponse:
    """Lo mismo que enviar, contando por el camino que esta haciendo el agente.

    Explorar un libro de once hojas lleva sus segundos. Ver "Mirando la hoja
    INVENTARIO" en vez de tres puntos es la diferencia entre esperar y dudar de
    si se ha colgado.
    """
    upload = await _read_upload(file)
    return StreamingResponse(
        _events(conversation_id, text, upload, container, session, owner_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(
    conversation_id: str,
    text: str,
    upload: tuple[str, bytes] | None,
    container: ContainerDep,
    session: SessionDep,
    owner_id: OwnerDep,
) -> AsyncIterator[str]:
    activities: asyncio.Queue[str | None] = asyncio.Queue()

    def watch(step: AgentStep) -> None:
        # Solo se retransmite lo que significa algo para quien espera. El
        # contenido crudo del modelo es largo y no le dice nada.
        if step.kind is StepKind.TOOL and step.content:
            activities.put_nowait(step.content)

    chat = container.chat(session)
    task = asyncio.create_task(
        chat.send(owner_id, conversation_id, text=text, upload=upload, observer=watch)
    )
    task.add_done_callback(lambda _: activities.put_nowait(None))

    while True:
        activity = await activities.get()
        if activity is None:
            break
        yield _event("activity", {"text": activity})

    try:
        turn = await task
    except DomainError as error:
        # La cabecera ya viajo: un fallo tardio solo puede llegar como evento.
        yield _event("error", as_payload(error).model_dump())
        return

    rendered = await chat.history(owner_id, conversation_id)
    by_id = {item.message.id: item for item in rendered}
    yield _event(
        "turn",
        TurnOut(
            user_message=MessageOut.plain(turn.user_message),
            assistant_message=MessageOut.of(
                by_id.get(turn.assistant_message.id)
                or RenderedMessage(message=turn.assistant_message)
            ),
            trace=TraceOut.of(turn.trace),
        ).model_dump(mode="json"),
    )


def _event(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _read_upload(file: UploadFile | None) -> tuple[str, bytes] | None:
    if file is None or not file.filename:
        return None
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("El archivo supera el tamano maximo admitido")
    return (file.filename, content)


def _artifact(
    artifact: Any,
    data: VisualData | None,
    preview: tuple[dict[str, object], ...],
    error: str | None,
) -> ArtifactOut:
    if isinstance(artifact, DatasetArtifact):
        return ArtifactOut(
            kind="dataset",
            dataset_id=artifact.dataset_id,
            name=artifact.name,
            row_count=artifact.row_count,
            columns=list(artifact.columns),
            origin=artifact.origin,
            warnings=list(artifact.warnings),
            preview=[dict(row) for row in preview],
            error=error,
        )
    if isinstance(artifact, VisualArtifact):
        return ArtifactOut(
            kind="visual",
            dataset_id=artifact.dataset_id,
            spec=artifact.spec,
            data=data,
            code=as_python(artifact.spec),
            error=error,
        )
    return ArtifactOut(kind="unknown", dataset_id="")
