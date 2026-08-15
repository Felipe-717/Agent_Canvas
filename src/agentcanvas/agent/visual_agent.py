"""El agente que traduce una peticion en lenguaje natural a una `VisualSpec`.

No genera codigo ni HTML: produce una especificacion declarativa que el motor
determinista ejecuta. Esa es la unica forma de que un modelo mas debil degrade
en "la grafica no es la que yo habria elegido" en vez de en "el dashboard no
carga".

Los mensajes de error de la validacion de dominio se le devuelven tal cual, asi
que la calidad de esos mensajes es la que determina si el agente se recupera.
"""

from __future__ import annotations

import json

from agentcanvas.agent.structured import StructuredGenerator, StructuredResult
from agentcanvas.domain.dataset.schema import DatasetSchema
from agentcanvas.domain.visual.spec import VisualSpec
from agentcanvas.domain.visual.validation import validate_spec

SYSTEM_PROMPT = """\
Eres un analista de datos que disena visualizaciones.

Recibes el esquema de un conjunto de datos y una peticion del usuario, y
devuelves la especificacion declarativa de una visualizacion.

Reglas:

1. Usa exactamente los nombres de columna del esquema. No inventes columnas ni
   uses los nombres originales del archivo.
2. Elige el tipo de grafico segun la pregunta, no segun lo que pida literalmente
   el usuario si no encaja:
   - evolucion en el tiempo: line
   - comparar categorias: bar
   - reparto sobre un total, pocas categorias: pie
   - un unico numero: kpi
   - relacion entre dos variables numericas: scatter (con aggregation "none")
   - detalle en filas: table
3. Con una columna de fecha en el eje, usa siempre `time_grain`. Por defecto
   "month", salvo que la peticion indique otra granularidad.
4. Las agregaciones "sum", "avg" y "median" solo valen sobre columnas numericas.
   Para contar usa "count", que puede ir sin columna.
5. Cuando el usuario pida un "top N" o "los mejores", usa `sort` con direccion
   "desc" y `limit` N.
6. `sort.by` no es un nombre de columna del esquema, sino una clave del
   resultado. Una dimension aporta su propio nombre (o "campo_grano" si lleva
   `time_grain`) y una medida aporta "agregacion_campo". Para ordenar por la
   suma de `valor` hay que escribir "sum_valor", no "valor".
7. `group_by` sirve para dividir en series. No lo uses si la peticion no lo
   pide, y nunca con la misma columna que el eje.
8. El `title` debe ser corto, descriptivo y en el idioma del usuario.

Responde solo con el objeto JSON de la especificacion."""

_USER_PROMPT = """\
Conjunto de datos: {name}

Columnas:
{columns}

Primeras filas:
{sample}

Peticion del usuario:
{instruction}"""


class VisualSpecAgent:
    def __init__(self, generator: StructuredGenerator) -> None:
        self._generator = generator

    async def propose(
        self,
        *,
        instruction: str,
        dataset_name: str,
        schema: DatasetSchema,
        sample: tuple[dict[str, object], ...] = (),
    ) -> StructuredResult[VisualSpec]:
        return await self._generator.generate(
            output=VisualSpec,
            name="visual_spec",
            system=SYSTEM_PROMPT,
            user=_USER_PROMPT.format(
                name=dataset_name,
                columns=describe_columns(schema),
                sample=_describe_sample(sample),
                instruction=instruction.strip(),
            ),
            validate=lambda spec: validate_spec(spec, schema),
        )


def describe_columns(schema: DatasetSchema) -> str:
    """Una linea por columna: nombre, tipo y el nombre original si difiere.

    El nombre original se incluye porque el usuario escribira "Región" y el
    modelo tiene que saber que eso es `region`.
    """
    lines: list[str] = []
    for column in schema.columns:
        line = f"- {column.name} ({column.type})"
        if column.original_name != column.name:
            line += f', en el archivo: "{column.original_name}"'
        lines.append(line)
    return "\n".join(lines)


def _describe_sample(sample: tuple[dict[str, object], ...]) -> str:
    if not sample:
        return "(no disponibles)"
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in sample)
