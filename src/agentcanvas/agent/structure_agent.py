"""El agente que averigua donde esta la tabla dentro de un archivo.

Mira el libro, hoja por hoja y ventana por ventana, hasta poder decir "la tabla
esta en la hoja X, la cabecera en la fila N". Si no puede decidirlo con
confianza, pregunta en vez de adivinar: un dataset extraido del sitio
equivocado produce graficos que parecen correctos y no lo son, que es el peor
fallo posible.

La propuesta se valida ejecutandola de verdad. El modelo no dice que su
extraccion funciona: se extrae, y si sale mal se le devuelve el motivo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from agentcanvas.agent.budget import Budget
from agentcanvas.agent.loop import AgentLoop, LoopResult
from agentcanvas.agent.structured import Observer
from agentcanvas.agent.tools import Toolbox, ToolOutcome, tool
from agentcanvas.application.ports.llm import LLMPort, Message
from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.application.ports.workbook import WorkbookReaderPort
from agentcanvas.domain.workbook.structure import TableSpec

MAX_PEEK_ROWS = 25
MAX_PEEK_COLUMNS = 15
PEEK_CELL_WIDTH = 20
"""Las celdas se recortan al ensenarlas. Para reconocer una cabecera basta con
el principio del texto, y las descripciones largas disparan el coste."""

MAX_SHEETS_PREVIEWED = 8
PREVIEW_ROWS = 4
PREVIEW_COLUMNS = 8
PREVIEW_CELL_WIDTH = 16

SYSTEM_PROMPT = """\
Eres un analista que prepara datos. Recibes un archivo de hoja de calculo y
tienes que averiguar donde esta la tabla de datos de verdad.

Los archivos reales no empiezan en A1 con cabeceras limpias. Suelen tener
titulos, instrucciones, filas de ejemplo, totales al pie, hojas auxiliares
vacias, y a veces varias tablas en la misma hoja puestas una al lado de otra.

Procedimiento:

1. Llama a `listar_hojas` para ver que hay.
2. Llama a `mirar` sobre las hojas prometedoras. Empieza por la fila 1 para ver
   que hay encima de la tabla. Mira mas de una ventana si hace falta.
3. Identifica la fila de cabecera: es la primera fila donde varias celdas
   seguidas parecen nombres de columna, no prosa.
4. Fijate en si hay que descartar filas: una fila de ejemplo justo debajo de la
   cabecera, o filas de TOTAL al final (usa `ultima_fila_datos` para cortarlas).
5. Si en la hoja hay varias tablas lado a lado, delimita las columnas de una
   sola con `primera_columna` y `ultima_columna`.
6. Llama a `proponer_tabla`. Se validara extrayendola de verdad; si algo esta
   mal, te lo dire y podras corregirlo.

Si el archivo tiene varias hojas con tablas de contenido distinto y el usuario
no ha dicho cual quiere, pregunta CUANTO ANTES: en cuanto lo veas en
`listar_hojas`, sin ir mirando hoja por hoja. Responde con texto, resume en una
linea que hay en cada una y pregunta cual le interesa.

No adivines nunca cual queria. Extraer la tabla equivocada produce graficos que
parecen correctos y no lo son, que es el peor fallo posible. Explorar de mas,
en cambio, solo cuesta tiempo y dinero: si con una hoja clara puedes resolverlo
en dos pasos, hazlo en dos.

Cuando termines o preguntes, hazlo en el idioma del usuario y sin tecnicismos:
habla de hojas, filas y columnas, no de specs ni de parsers."""


class StructureProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    spec: TableSpec
    table: NormalizedTable
    explanation: str


class WorkbookStructureAgent:
    def __init__(
        self,
        llm: LLMPort,
        reader: WorkbookReaderPort,
        *,
        budget: Budget | None = None,
    ) -> None:
        self._loop = AgentLoop(llm, budget or Budget(max_iterations=12))
        self._reader = reader

    async def inspect(
        self,
        source: Path,
        *,
        destination: Path,
        filename: str,
        instruction: str | None = None,
        history: tuple[Message, ...] = (),
        observer: Observer | None = None,
    ) -> LoopResult:
        """Explora el archivo. Devuelve una propuesta o una pregunta.

        `history` permite continuar tras la respuesta del usuario, que es lo que
        hace posible "usa la hoja INVENTARIO" como turno siguiente.
        """
        messages = list(history) or [Message.system(SYSTEM_PROMPT)]
        messages.append(Message.user(_opening(filename, instruction)))
        toolbox = self._toolbox(source, destination)
        return await self._loop.run(messages, toolbox, observer=observer)

    def _toolbox(self, source: Path, destination: Path) -> Toolbox:
        async def listar_hojas(_: dict[str, Any]) -> ToolOutcome:
            """Resumen con asomo incluido.

            Devolver solo nombres obliga al agente a llamar a `mirar` una vez
            por hoja: con once hojas eso son once vueltas y un contexto enorme.
            Adelantar las primeras filas de cada una cuesta lo mismo que una
            sola llamada y suele bastar para decidir.
            """
            overview = self._reader.overview(source)
            blocks: list[str] = []
            for sheet in overview.candidates[:MAX_SHEETS_PREVIEWED]:
                window = self._reader.peek(
                    source, sheet=sheet.name, rows=PREVIEW_ROWS, columns=PREVIEW_COLUMNS
                )
                blocks.append(
                    f"- '{sheet.name}': {sheet.rows} filas x {sheet.columns} columnas, "
                    f"{sheet.filled_cells} celdas\n{window.render(PREVIEW_CELL_WIDTH)}"
                )
            rest = [sheet.name for sheet in overview.candidates[MAX_SHEETS_PREVIEWED:]]
            if rest:
                blocks.append(f"Otras hojas con contenido: {', '.join(rest)}")
            empties = [sheet.name for sheet in overview.sheets if sheet.filled_cells == 0]
            if empties:
                blocks.append(f"Hojas vacias (ignoralas): {', '.join(empties)}")
            return ToolOutcome(
                message=(
                    "Hojas del archivo, con sus primeras filas. El numero de la "
                    "izquierda es la fila:\n\n" + "\n\n".join(blocks)
                )
            )

        async def mirar(arguments: dict[str, Any]) -> ToolOutcome:
            window = self._reader.peek(
                source,
                sheet=str(arguments["hoja"]),
                first_row=max(1, int(arguments.get("fila_inicial", 1))),
                rows=min(MAX_PEEK_ROWS, int(arguments.get("filas", 12))),
                first_column=max(1, int(arguments.get("columna_inicial", 1))),
                columns=min(MAX_PEEK_COLUMNS, int(arguments.get("columnas", 10))),
            )
            return ToolOutcome(
                message=(
                    f"Hoja '{window.sheet}', desde la columna {window.first_column}. "
                    f"El numero de la izquierda es la fila:\n"
                    f"{window.render(PEEK_CELL_WIDTH)}"
                )
            )

        async def proponer_tabla(arguments: dict[str, Any]) -> ToolOutcome:
            try:
                spec = TableSpec(
                    sheet=str(arguments["hoja"]),
                    header_row=int(arguments["fila_cabecera"]),
                    first_data_row=_optional_int(arguments.get("primera_fila_datos")),
                    last_data_row=_optional_int(arguments.get("ultima_fila_datos")),
                    first_column=int(arguments.get("primera_columna", 1)),
                    last_column=_optional_int(arguments.get("ultima_columna")),
                    skip_rows=tuple(int(row) for row in arguments.get("filas_a_descartar", [])),
                )
            except (ValidationError, ValueError, TypeError) as error:
                return ToolOutcome(message=f"Esa propuesta no es coherente: {error}")

            # La prueba de verdad: extraerla. El modelo no dice que funciona.
            table = self._reader.extract(source, spec, destination=destination)
            if table.row_count == 0:
                return ToolOutcome(
                    message=(
                        "Con esas coordenadas no sale ninguna fila de datos. "
                        "Revisa la fila de cabecera y el rango."
                    )
                )
            explanation = str(arguments.get("explicacion", "")).strip()
            return ToolOutcome(
                message=(
                    f"Extraida correctamente: {table.row_count} filas y "
                    f"{len(table.schema_.columns)} columnas "
                    f"({', '.join(table.schema_.column_names)})."
                ),
                payload=StructureProposal(spec=spec, table=table, explanation=explanation),
                done=True,
            )

        return Toolbox(
            [
                tool(
                    name="listar_hojas",
                    description=(
                        "Lista las hojas del archivo con su tamano y cuanto contenido tienen."
                    ),
                    parameters={"type": "object", "properties": {}},
                    handler=listar_hojas,
                ),
                tool(
                    name="mirar",
                    description=(
                        "Muestra las celdas de una zona de una hoja, con los numeros de fila. "
                        "Usalo para encontrar donde empieza la tabla."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "hoja": {"type": "string"},
                            "fila_inicial": {"type": "integer", "minimum": 1},
                            "filas": {"type": "integer", "minimum": 1, "maximum": MAX_PEEK_ROWS},
                            "columna_inicial": {"type": "integer", "minimum": 1},
                            "columnas": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": MAX_PEEK_COLUMNS,
                            },
                        },
                        "required": ["hoja"],
                    },
                    handler=mirar,
                ),
                tool(
                    name="proponer_tabla",
                    description=(
                        "Declara donde esta la tabla. Se valida extrayendola de verdad. "
                        "Todas las coordenadas empiezan en 1, como en Excel."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "hoja": {"type": "string"},
                            "fila_cabecera": {"type": "integer", "minimum": 1},
                            "primera_fila_datos": {"type": "integer", "minimum": 1},
                            "ultima_fila_datos": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Para cortar antes de una fila de totales.",
                            },
                            "primera_columna": {"type": "integer", "minimum": 1},
                            "ultima_columna": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "Aisla una tabla de varias puestas lado a lado.",
                            },
                            "filas_a_descartar": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Filas sueltas a ignorar, como una fila de ejemplo.",
                            },
                            "explicacion": {
                                "type": "string",
                                "description": "Una frase para el usuario sobre que tabla es esta.",
                            },
                        },
                        "required": ["hoja", "fila_cabecera"],
                    },
                    handler=proponer_tabla,
                ),
            ]
        )


def _opening(filename: str, instruction: str | None) -> str:
    text = f"El usuario ha subido el archivo '{filename}'. Averigua donde estan los datos."
    if instruction:
        text += f"\n\nAdemas ha dicho: {instruction}"
    return text


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
