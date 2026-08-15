"""Prueba de humo contra el modelo real.

Es la unica cosa del repositorio que gasta cuota. Todo lo demas se testea con
`FakeLLM`. Se ejecuta a mano, nunca en la bateria de tests:

    python scripts/smoke_visual.py
    python scripts/smoke_visual.py "top 3 productos por venta"

Crea su propio directorio de datos en var/smoke, asi que no toca nada de lo que
haya en desarrollo. Coste tipico: menos de un centimo.
"""

from __future__ import annotations

import asyncio
import json
import sys

from agentcanvas.application.use_cases.create_visual import (
    CreateVisualCommand,
    CreateVisualResult,
)
from agentcanvas.application.use_cases.ingest_file import IngestFileCommand
from agentcanvas.bootstrap.container import Container, build_container
from agentcanvas.config import Settings, get_settings
from agentcanvas.infrastructure.persistence.models import Base

VENTAS = (
    "Fecha,Región,Producto,Cantidad,Valor Total\n"
    "2026-01-15,Norte,Teclado,3,150.00\n"
    "2026-01-22,Sur,Monitor,1,320.00\n"
    "2026-01-28,Norte,Raton,5,75.50\n"
    "2026-02-03,Este,Monitor,2,640.00\n"
    "2026-02-14,Norte,Teclado,4,200.00\n"
    "2026-02-19,Sur,Raton,7,105.70\n"
    "2026-03-02,Este,Teclado,2,100.00\n"
    "2026-03-11,Norte,Monitor,3,960.00\n"
    "2026-03-19,Sur,Teclado,6,300.00\n"
    "2026-03-25,Este,Raton,9,135.90\n"
).encode()

DEFAULT_INSTRUCTION = "Muestrame la evolucion de las ventas por region"


async def main(instruction: str) -> int:
    settings = _settings()
    if not settings.llm_api_key.get_secret_value():
        print("Falta LLM_API_KEY en el .env. Sin clave no se puede probar el modelo real.")
        return 1

    container = build_container(settings)
    async with container.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        print(f"Modelo: {settings.llm_model}  ({settings.llm_base_url})")
        print(f"Peticion: {instruction}\n")
        result = await _run(container, instruction)
    finally:
        await container.engine.dispose()

    _report(result)
    return 0


def _settings() -> Settings:
    base = get_settings()
    # Directorio propio: la prueba no debe ensuciar los datos de desarrollo.
    return base.model_copy(update={"data_dir": base.data_dir / "smoke", "database_url": ""})


async def _run(container: Container, instruction: str) -> CreateVisualResult:
    session = container.session_factory()
    try:
        ingested = await container.ingest_file(session).execute(
            IngestFileCommand(
                owner_id=container.settings.default_owner_id,
                filename="ventas.csv",
                content=VENTAS,
                dataset_name="ventas",
            )
        )
        print("Esquema detectado:")
        for column in ingested.dataset.schema_.columns:
            print(f"  {column.name} ({column.type})")
        print()

        return await container.create_visual(session).execute(
            CreateVisualCommand(
                owner_id=container.settings.default_owner_id,
                dataset_id=ingested.dataset.id,
                instruction=instruction,
            )
        )
    finally:
        await session.close()


def _report(result: CreateVisualResult) -> None:
    print("Especificacion propuesta:")
    print(json.dumps(result.spec.model_dump(mode="json", exclude_none=True), indent=2))
    print("\nDatos calculados:")
    for row in result.data.rows:
        print(f"  {row}")

    usage = result.trace.usage
    cost = usage.input_tokens * 0.20e-6 + usage.output_tokens * 1.20e-6
    print(
        f"\nIntentos: {result.trace.repairs + 1}"
        f"  |  tokens: {usage.input_tokens} entrada, {usage.output_tokens} salida"
        f"  |  coste aproximado: ${cost:.5f}"
    )


if __name__ == "__main__":
    argument = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INSTRUCTION
    raise SystemExit(asyncio.run(main(argument)))
