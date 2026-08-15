"""El caso de uso central: hablar con el asistente.

Aqui se juntan todas las piezas. El agente conversa, y cuando hace falta usa
herramientas que exploran un archivo adjunto, preparan una tabla o dibujan un
grafico. Lo que produce se guarda como artefactos del mensaje.

Las herramientas se construyen en esta capa y no en `agent` porque necesitan
repositorios y almacenamiento. El agente solo ve un `Toolbox`: sigue sin saber
que existe una base de datos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agentcanvas.agent.budget import Budget
from agentcanvas.agent.chat_prompt import SYSTEM_PROMPT
from agentcanvas.agent.loop import AgentLoop
from agentcanvas.agent.structured import Observer
from agentcanvas.agent.tools import Toolbox, ToolOutcome, tool
from agentcanvas.agent.trace import AgentTrace
from agentcanvas.application.ports.llm import LLMPort, Message, Role
from agentcanvas.application.ports.query import QueryEnginePort
from agentcanvas.application.ports.repositories import (
    ConversationRepositoryPort,
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.workbook import WorkbookReaderPort
from agentcanvas.domain.chat.entities import (
    Attachment,
    ChatMessage,
    Conversation,
    DatasetArtifact,
    MessageContent,
    MessageRole,
    VisualArtifact,
)
from agentcanvas.domain.dataset.entities import Dataset, StoredFile
from agentcanvas.domain.shared.clock import utcnow
from agentcanvas.domain.shared.errors import NotFoundError
from agentcanvas.domain.shared.identifiers import new_id
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.domain.visual.validation import validate_spec
from agentcanvas.domain.workbook.structure import TableSpec

PEEK_CELL_WIDTH = 20
PREVIEW_ROWS = 4
PREVIEW_COLUMNS = 8
PREVIEW_CELL_WIDTH = 16
MAX_SHEETS_PREVIEWED = 8


class ChatTurn(BaseModel):
    """Lo que sale de un turno: el mensaje del usuario y el del asistente."""

    model_config = ConfigDict(frozen=True)

    user_message: ChatMessage
    assistant_message: ChatMessage
    trace: AgentTrace


class RenderedMessage(BaseModel):
    """Un mensaje listo para pintar, con sus visuales ya recalculados."""

    model_config = ConfigDict(frozen=True)

    message: ChatMessage
    data: dict[str, VisualData] = {}
    """Datos de cada visual, indexados por el id del dataset y la posicion."""

    errors: dict[str, str] = {}


class ChatService:
    def __init__(
        self,
        *,
        llm: LLMPort,
        conversations: ConversationRepositoryPort,
        datasets: DatasetRepositoryPort,
        files: StoredFileRepositoryPort,
        storage: FileStoragePort,
        workbook: WorkbookReaderPort,
        engine: QueryEnginePort,
        uow: UnitOfWorkPort,
        budget: Budget | None = None,
    ) -> None:
        self._llm = llm
        self._conversations = conversations
        self._datasets = datasets
        self._files = files
        self._storage = storage
        self._workbook = workbook
        self._engine = engine
        self._uow = uow
        self._loop = AgentLoop(llm, budget or Budget(max_iterations=14))

    # ------------------------------------------------------------ conversacion

    async def start(self, owner_id: str) -> Conversation:
        conversation = Conversation(owner_id=owner_id)
        await self._conversations.add(conversation)
        await self._uow.commit()
        return conversation

    async def list_conversations(self, owner_id: str) -> list[Conversation]:
        return await self._conversations.list_for_owner(owner_id)

    async def delete(self, owner_id: str, conversation_id: str) -> None:
        await self._require(owner_id, conversation_id)
        await self._conversations.delete(conversation_id)
        await self._uow.commit()

    async def history(self, owner_id: str, conversation_id: str) -> list[RenderedMessage]:
        """Los mensajes con sus visuales recalculados contra los datos de hoy."""
        await self._require(owner_id, conversation_id)
        messages = await self._conversations.list_messages(conversation_id)
        return [await self._render(message) for message in messages]

    # ------------------------------------------------------------------- turno

    async def send(
        self,
        owner_id: str,
        conversation_id: str,
        *,
        text: str,
        upload: tuple[str, bytes] | None = None,
        observer: Observer | None = None,
    ) -> ChatTurn:
        conversation = await self._require(owner_id, conversation_id)

        attachments: list[Attachment] = []
        if upload is not None:
            attachments.append(await self._store(owner_id, *upload))

        user_message = ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            text=text,
            content=MessageContent(attachments=tuple(attachments)),
        )
        await self._conversations.add_message(user_message)

        history = await self._conversations.list_messages(conversation_id)
        prompt = await self._build_prompt(history, owner_id)
        collected = _Collected()
        result = await self._loop.run(
            prompt, self._toolbox(owner_id, conversation_id, collected), observer=observer
        )

        assistant_message = ChatMessage(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            text=result.text or _fallback(collected),
            content=MessageContent(artifacts=tuple(collected.artifacts)),
        )
        await self._conversations.add_message(assistant_message)

        if conversation.title == Conversation(owner_id=owner_id).title and text.strip():
            conversation = conversation.titled_from(text)
        conversation = conversation.model_copy(update={"updated_at": utcnow()})
        await self._conversations.update(conversation)
        await self._uow.commit()

        return ChatTurn(
            user_message=user_message,
            assistant_message=assistant_message,
            trace=result.trace,
        )

    # --------------------------------------------------------------- interiores

    async def _require(self, owner_id: str, conversation_id: str) -> Conversation:
        conversation = await self._conversations.get(conversation_id)
        if conversation is None or conversation.owner_id != owner_id:
            raise NotFoundError("conversacion", conversation_id)
        return conversation

    async def _store(self, owner_id: str, filename: str, content: bytes) -> Attachment:
        import hashlib
        from pathlib import PurePath

        file_id = new_id("file")
        extension = PurePath(filename).suffix.lower() or ".bin"
        key = f"uploads/{file_id}{extension}"
        self._storage.save(content, key=key)
        await self._files.add(
            StoredFile(
                id=file_id,
                owner_id=owner_id,
                original_filename=filename,
                extension=extension,
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                storage_key=key,
            )
        )
        return Attachment(file_id=file_id, filename=filename)

    async def _build_prompt(self, history: list[ChatMessage], owner_id: str) -> list[Message]:
        """Traduce la conversacion guardada a mensajes para el modelo.

        Los artefactos se resumen en una linea. Reenviar los datos de cada
        grafico multiplicaria el coste de cada turno sin decirle nada nuevo: el
        modelo ya sabe lo que dibujo, y si necesita cifras, las consulta.
        """
        messages: list[Message] = [Message.system(SYSTEM_PROMPT)]
        for entry in history:
            if entry.role is MessageRole.USER:
                text = entry.text
                for attachment in entry.attachments:
                    text += (
                        f"\n[archivo adjunto: '{attachment.filename}', "
                        f"id {attachment.file_id}]"
                    )
                messages.append(Message.user(text))
            else:
                summary = "\n".join(_describe(artifact) for artifact in entry.artifacts)
                messages.append(Message.assistant("\n".join(filter(None, [entry.text, summary]))))

        available = await self._available_datasets(owner_id)
        if available:
            messages.append(Message.system(available))
        return messages

    async def _available_datasets(self, owner_id: str) -> str:
        datasets = await self._datasets.list_for_owner(owner_id)
        if not datasets:
            return ""
        lines = [
            f"- id {dataset.id}: '{dataset.name}', {dataset.row_count} filas, "
            f"columnas: {', '.join(dataset.schema_.column_names)}"
            for dataset in datasets[:10]
        ]
        return "Conjuntos de datos ya preparados:\n" + "\n".join(lines)

    async def _render(self, message: ChatMessage) -> RenderedMessage:
        data: dict[str, VisualData] = {}
        errors: dict[str, str] = {}
        for index, artifact in enumerate(message.artifacts):
            if not isinstance(artifact, VisualArtifact):
                continue
            key = str(index)
            try:
                data[key] = await self._execute(artifact.dataset_id, artifact.spec)
            except Exception as error:
                # Un grafico que ya no se puede calcular no puede impedir leer
                # la conversacion.
                errors[key] = str(error)
        return RenderedMessage(message=message, data=data, errors=errors)

    async def _execute(self, dataset_id: str, spec: VisualSpec) -> VisualData:
        dataset = await self._datasets.get(dataset_id)
        if dataset is None or dataset.current_version_id is None:
            raise LookupError("El conjunto de datos ya no esta disponible")
        version = await self._datasets.get_version(dataset.current_version_id)
        if version is None:
            raise LookupError("No se encuentra la version activa")
        return self._engine.execute(
            spec, source=self._storage.path_for(version.storage_key), schema=dataset.schema_
        )

    # ------------------------------------------------------------- herramientas

    def _toolbox(self, owner_id: str, conversation_id: str, collected: _Collected) -> Toolbox:
        async def _file(file_id: str) -> tuple[StoredFile, Path]:
            stored = await self._files.get(file_id)
            if stored is None or stored.owner_id != owner_id:
                raise ValueError(f"No hay ningun archivo con id '{file_id}' en esta conversacion")
            return stored, self._storage.path_for(stored.storage_key)

        async def listar_hojas(arguments: dict[str, Any]) -> ToolOutcome:
            _, path = await _file(str(arguments["archivo"]))
            overview = self._workbook.overview(path)
            blocks: list[str] = []
            for sheet in overview.candidates[:MAX_SHEETS_PREVIEWED]:
                window = self._workbook.peek(
                    path, sheet=sheet.name, rows=PREVIEW_ROWS, columns=PREVIEW_COLUMNS
                )
                blocks.append(
                    f"- '{sheet.name}': {sheet.rows} filas x {sheet.columns} columnas, "
                    f"{sheet.filled_cells} celdas\n{window.render(PREVIEW_CELL_WIDTH)}"
                )
            empties = [s.name for s in overview.sheets if s.filled_cells == 0]
            if empties:
                blocks.append(f"Hojas vacias (ignoralas): {', '.join(empties)}")
            return ToolOutcome(
                message=(
                    "Hojas del archivo, con sus primeras filas. El numero de la "
                    "izquierda es la fila:\n\n" + "\n\n".join(blocks)
                )
            )

        async def mirar(arguments: dict[str, Any]) -> ToolOutcome:
            _, path = await _file(str(arguments["archivo"]))
            window = self._workbook.peek(
                path,
                sheet=str(arguments["hoja"]),
                first_row=max(1, int(arguments.get("fila_inicial", 1))),
                rows=min(25, int(arguments.get("filas", 12))),
                first_column=max(1, int(arguments.get("columna_inicial", 1))),
                columns=min(15, int(arguments.get("columnas", 10))),
            )
            return ToolOutcome(
                message=(
                    f"Hoja '{window.sheet}', desde la columna {window.first_column}. "
                    f"El numero de la izquierda es la fila:\n{window.render(PEEK_CELL_WIDTH)}"
                )
            )

        async def preparar_datos(arguments: dict[str, Any]) -> ToolOutcome:
            stored, path = await _file(str(arguments["archivo"]))
            try:
                spec = TableSpec(
                    sheet=str(arguments["hoja"]),
                    header_row=int(arguments["fila_cabecera"]),
                    first_data_row=_optional_int(arguments.get("primera_fila_datos")),
                    last_data_row=_optional_int(arguments.get("ultima_fila_datos")),
                    first_column=int(arguments.get("primera_columna", 1)),
                    last_column=_optional_int(arguments.get("ultima_columna")),
                    skip_rows=tuple(int(r) for r in arguments.get("filas_a_descartar", [])),
                )
            except (ValidationError, ValueError, TypeError) as error:
                return ToolOutcome(message=f"Esa propuesta no es coherente: {error}")

            dataset_id = new_id("ds")
            key = f"datasets/{dataset_id}/{stored.id}.parquet"
            table = self._workbook.extract(
                path, spec, destination=self._storage.path_for(key)
            )

            name = str(arguments.get("nombre") or "").strip() or spec.sheet
            dataset = Dataset(
                id=dataset_id, owner_id=owner_id, name=name, schema=table.schema_
            )
            version = dataset.new_version(
                source_file_id=stored.id,
                storage_key=key,
                row_count=table.row_count,
                incoming_schema=table.schema_,
            )
            dataset.activate(version)
            await self._datasets.add(dataset)
            await self._datasets.add_version(version)

            collected.artifacts.append(
                DatasetArtifact(
                    dataset_id=dataset.id,
                    name=name,
                    row_count=table.row_count,
                    columns=table.schema_.column_names,
                    origin=spec.describe(),
                )
            )
            return ToolOutcome(
                message=(
                    f"Listo. Conjunto de datos '{name}' con id {dataset.id}: "
                    f"{table.row_count} filas y columnas "
                    f"{', '.join(table.schema_.column_names)}.\n"
                    f"Primeras filas: {list(table.preview[:3])}"
                )
            )

        async def crear_visual(arguments: dict[str, Any]) -> ToolOutcome:
            dataset_id = str(arguments.get("dataset_id", ""))
            dataset = await self._datasets.get(dataset_id)
            if dataset is None or dataset.owner_id != owner_id:
                return ToolOutcome(
                    message=(
                        f"No hay ningun conjunto de datos con id '{dataset_id}'. "
                        "Prepara primero los datos con `preparar_datos`."
                    )
                )
            try:
                spec = VisualSpec.model_validate(arguments.get("especificacion", {}))
            except ValidationError as error:
                return ToolOutcome(message=f"La especificacion no es valida: {error}")

            problems = validate_spec(spec, dataset.schema_)
            if problems:
                return ToolOutcome(message="No se puede dibujar:\n- " + "\n- ".join(problems))

            data = await self._execute(dataset_id, spec)
            collected.artifacts.append(VisualArtifact(dataset_id=dataset_id, spec=spec))
            return ToolOutcome(
                message=(
                    f"Grafico '{spec.title}' dibujado ({spec.type}, {len(data.rows)} "
                    "puntos). El usuario ya lo esta viendo."
                )
            )

        return Toolbox(
            [
                tool(
                    name="listar_hojas",
                    description="Lista las hojas de un archivo adjunto con sus primeras filas.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "archivo": {"type": "string", "description": "id del archivo"}
                        },
                        "required": ["archivo"],
                    },
                    handler=listar_hojas,
                ),
                tool(
                    name="mirar",
                    description="Muestra celdas de una zona de una hoja, con los numeros de fila.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "archivo": {"type": "string"},
                            "hoja": {"type": "string"},
                            "fila_inicial": {"type": "integer", "minimum": 1},
                            "filas": {"type": "integer", "minimum": 1, "maximum": 25},
                            "columna_inicial": {"type": "integer", "minimum": 1},
                            "columnas": {"type": "integer", "minimum": 1, "maximum": 15},
                        },
                        "required": ["archivo", "hoja"],
                    },
                    handler=mirar,
                ),
                tool(
                    name="preparar_datos",
                    description=(
                        "Extrae una tabla del archivo y la deja lista para consultar. "
                        "Coordenadas en base 1, como en Excel."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "archivo": {"type": "string"},
                            "hoja": {"type": "string"},
                            "fila_cabecera": {"type": "integer", "minimum": 1},
                            "primera_fila_datos": {"type": "integer", "minimum": 1},
                            "ultima_fila_datos": {"type": "integer", "minimum": 1},
                            "primera_columna": {"type": "integer", "minimum": 1},
                            "ultima_columna": {"type": "integer", "minimum": 1},
                            "filas_a_descartar": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "nombre": {"type": "string"},
                        },
                        "required": ["archivo", "hoja", "fila_cabecera"],
                    },
                    handler=preparar_datos,
                ),
                tool(
                    name="crear_visual",
                    description="Dibuja una visualizacion sobre un conjunto de datos preparado.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "dataset_id": {"type": "string"},
                            "especificacion": VisualSpec.model_json_schema(),
                        },
                        "required": ["dataset_id", "especificacion"],
                    },
                    handler=crear_visual,
                ),
            ]
        )


class _Collected:
    """Los artefactos que las herramientas van produciendo durante el turno."""

    def __init__(self) -> None:
        self.artifacts: list[Any] = []


def _describe(artifact: Any) -> str:
    if isinstance(artifact, DatasetArtifact):
        return (
            f"[preparado el conjunto '{artifact.name}' id {artifact.dataset_id}: "
            f"{artifact.row_count} filas, columnas {', '.join(artifact.columns)}]"
        )
    if isinstance(artifact, VisualArtifact):
        return f"[dibujado el grafico '{artifact.spec.title}' ({artifact.spec.type})]"
    return ""


def _fallback(collected: _Collected) -> str:
    """Si el agente termino por herramienta y no dijo nada, se dice por el."""
    if not collected.artifacts:
        return "Listo."
    last = collected.artifacts[-1]
    if isinstance(last, VisualArtifact):
        return f"Aquí tienes: {last.spec.title}."
    if isinstance(last, DatasetArtifact):
        return f"He preparado '{last.name}' con {last.row_count} filas."
    return "Listo."


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


__all__ = ["ChatService", "ChatTurn", "RenderedMessage", "Role"]
