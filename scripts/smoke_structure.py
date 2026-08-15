"""Prueba de humo del agente de estructura contra un archivo real.

    python scripts/smoke_structure.py "C:\\ruta\\archivo.xlsx"
    python scripts/smoke_structure.py "archivo.xlsx" "usa la hoja INVENTARIO"

Gasta cuota. Imprime cada herramienta que el agente decide usar, para poder ver
como razona y no solo en que acaba.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from agentcanvas.agent.structure_agent import StructureProposal, WorkbookStructureAgent
from agentcanvas.agent.trace import AgentStep, StepKind
from agentcanvas.config import get_settings
from agentcanvas.infrastructure.llm.factory import build_llm
from agentcanvas.infrastructure.tabular.workbook_reader import OpenpyxlWorkbookReader


async def main(path: Path, instruction: str | None) -> int:
    settings = get_settings()
    if not settings.llm_api_key.get_secret_value():
        print("Falta LLM_API_KEY en el .env.")
        return 1

    agent = WorkbookStructureAgent(build_llm(settings), OpenpyxlWorkbookReader())
    destination = Path(tempfile.mkdtemp()) / "tabla.parquet"

    print(f"Archivo: {path.name}")
    if instruction:
        print(f"Instruccion: {instruction}")
    print()

    result = await agent.inspect(
        path,
        destination=destination,
        filename=path.name,
        instruction=instruction,
        observer=_show,
    )

    print()
    if isinstance(result.payload, StructureProposal):
        proposal = result.payload
        print("PROPUESTA")
        print("  ", proposal.spec.describe())
        if proposal.explanation:
            print("  ", proposal.explanation)
        print("   filas:", proposal.table.row_count)
        print("   columnas:", ", ".join(proposal.table.schema_.column_names))
        print("   muestra:", proposal.table.preview[0] if proposal.table.preview else "—")
    else:
        print("EL AGENTE PREGUNTA")
        print("  ", result.text)

    usage = result.trace.usage
    cost = usage.input_tokens * 0.20e-6 + usage.output_tokens * 1.20e-6
    print(
        f"\nIteraciones: {result.trace.iterations}"
        f"  |  tokens: {usage.input_tokens} entrada ({usage.cached_input_tokens} en cache),"
        f" {usage.output_tokens} salida"
        f"  |  coste aproximado: ${cost:.5f}"
    )
    return 0


def _show(step: AgentStep) -> None:
    if step.kind is StepKind.PROPOSAL and step.content:
        print(f"  [{step.iteration}] el agente dice: {step.content[:160]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    argument = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(asyncio.run(main(Path(sys.argv[1]), argument)))
