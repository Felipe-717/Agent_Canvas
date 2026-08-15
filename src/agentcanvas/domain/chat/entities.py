"""La conversacion, que es la entidad principal del producto.

No se organiza alrededor de los archivos: se organiza alrededor de lo que el
usuario dice. Un archivo es un adjunto de un mensaje, igual que en cualquier
chat, y puede llegar en el primer turno o en el decimo, o no llegar nunca.

Un mensaje del asistente puede traer artefactos: un conjunto de datos que acaba
de preparar, o una visualizacion. De la visualizacion se guarda su
especificacion, nunca sus numeros; al reabrir la conversacion se recalculan.
Asi una conversacion de hace un mes muestra los datos de hoy.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.domain.shared.clock import utcnow
from agentcanvas.domain.shared.identifiers import new_id
from agentcanvas.domain.visual.spec import VisualSpec

TITLE_LENGTH = 60


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Attachment(BaseModel):
    """Un archivo que el usuario adjunto a su mensaje."""

    model_config = ConfigDict(frozen=True)

    file_id: str
    filename: str


class DatasetArtifact(BaseModel):
    """El asistente consiguio extraer una tabla y dejarla lista para consultar."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["dataset"] = "dataset"
    dataset_id: str
    name: str
    row_count: int
    columns: tuple[str, ...]
    origin: str
    """De donde salio, en palabras: "hoja Contactos, cabecera en la fila 11"."""


class VisualArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["visual"] = "visual"
    dataset_id: str
    spec: VisualSpec
    """Sin datos a proposito. Se recalculan al abrir la conversacion, que es lo
    que hace que un grafico de hace un mes muestre las cifras de hoy."""


Artifact = Annotated[DatasetArtifact | VisualArtifact, Field(discriminator="kind")]


class MessageContent(BaseModel):
    """Todo lo que acompana al texto de un mensaje.

    Va junto en una sola columna JSON: son datos que solo tienen sentido dentro
    de su mensaje y que nunca se consultan por separado.
    """

    model_config = ConfigDict(frozen=True)

    attachments: tuple[Attachment, ...] = ()
    artifacts: tuple[Artifact, ...] = ()


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: new_id("msg"))
    conversation_id: str
    role: MessageRole
    text: str = ""
    content: MessageContent = MessageContent()
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def attachments(self) -> tuple[Attachment, ...]:
        return self.content.attachments

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return self.content.artifacts

    @property
    def visuals(self) -> tuple[VisualArtifact, ...]:
        return tuple(a for a in self.artifacts if isinstance(a, VisualArtifact))

    @property
    def datasets(self) -> tuple[DatasetArtifact, ...]:
        return tuple(a for a in self.artifacts if isinstance(a, DatasetArtifact))


class Conversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: new_id("conv"))
    owner_id: str
    title: str = "Nueva conversación"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def titled_from(self, first_message: str) -> Conversation:
        """Toma el titulo del primer mensaje del usuario.

        Pedirle un titulo al modelo costaria una llamada entera para algo que el
        usuario ya escribio.
        """
        clean = " ".join(first_message.split())
        if not clean:
            return self
        title = clean if len(clean) <= TITLE_LENGTH else clean[: TITLE_LENGTH - 1].rstrip() + "…"
        return self.model_copy(update={"title": title, "updated_at": utcnow()})
