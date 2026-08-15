from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import BaseModel

from agentcanvas.application.use_cases.chat import RenderedMessage
from agentcanvas.domain.chat.entities import (
    ChatMessage,
    Conversation,
    DatasetArtifact,
    VisualArtifact,
)
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.infrastructure.web.dependencies import ContainerDep, OwnerDep, SessionDep
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
    spec: VisualSpec | None = None
    data: VisualData | None = None
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
                _artifact(artifact, rendered.data.get(str(index)), rendered.errors.get(str(index)))
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
    upload: tuple[str, bytes] | None = None
    if file is not None and file.filename:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("El archivo supera el tamano maximo admitido")
        upload = (file.filename, content)

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


def _artifact(artifact: Any, data: VisualData | None, error: str | None) -> ArtifactOut:
    if isinstance(artifact, DatasetArtifact):
        return ArtifactOut(
            kind="dataset",
            dataset_id=artifact.dataset_id,
            name=artifact.name,
            row_count=artifact.row_count,
            columns=list(artifact.columns),
            origin=artifact.origin,
        )
    if isinstance(artifact, VisualArtifact):
        return ArtifactOut(
            kind="visual",
            dataset_id=artifact.dataset_id,
            spec=artifact.spec,
            data=data,
            error=error,
        )
    return ArtifactOut(kind="unknown", dataset_id="")
