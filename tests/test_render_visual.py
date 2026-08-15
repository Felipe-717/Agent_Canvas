"""La promesa del producto, verificada de extremo a extremo.

Un grafico guardado como spec, un archivo nuevo del mes siguiente, y el mismo
grafico recalculado sin intervencion de nadie ni una sola llamada al modelo.
"""

from __future__ import annotations

import pytest

from agentcanvas.application.use_cases.ingest_file import IngestFileCommand, IngestFileResult
from agentcanvas.application.use_cases.render_visual import (
    DatasetHasNoDataError,
    RenderVisualCommand,
)
from agentcanvas.bootstrap.container import Container
from agentcanvas.domain.dataset.entities import Dataset
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import (
    Aggregation,
    ChartType,
    Dimension,
    Measure,
    Sort,
    VisualSpec,
)
from agentcanvas.domain.visual.validation import validate_spec
from agentcanvas.infrastructure.persistence.repositories import SqlAlchemyDatasetRepository
from tests.conftest import OWNER

ENERO = (
    b"fecha,region,valor\n"
    b"2026-01-15,Norte,100.0\n"
    b"2026-01-20,Sur,150.0\n"
)
FEBRERO = (
    b"fecha,region,valor\n"
    b"2026-02-10,Norte,120.0\n"
    b"2026-02-11,Sur,90.0\n"
    b"2026-02-12,Este,60.0\n"
)

VENTAS_POR_REGION = VisualSpec(
    type=ChartType.BAR,
    title="Ventas por región",
    x=Dimension(field="region"),
    y=(Measure(field="valor", aggregation=Aggregation.SUM),),
    sort=Sort(by="sum_valor"),
)


async def _ingest(
    container: Container, content: bytes, *, dataset_id: str | None = None
) -> IngestFileResult:
    session = container.session_factory()
    try:
        return await container.ingest_file(session).execute(
            IngestFileCommand(
                owner_id=OWNER,
                filename="ventas.csv",
                content=content,
                dataset_id=dataset_id,
            )
        )
    finally:
        await session.close()


async def _render(container: Container, dataset_id: str, spec: VisualSpec) -> VisualData:
    session = container.session_factory()
    try:
        return await container.render_visual(session).execute(
            RenderVisualCommand(owner_id=OWNER, dataset_id=dataset_id, spec=spec)
        )
    finally:
        await session.close()


async def test_a_visual_renders_against_the_active_version(container: Container) -> None:
    enero = await _ingest(container, ENERO)

    data = await _render(container, enero.dataset.id, VENTAS_POR_REGION)

    assert {row["region"]: row["sum_valor"] for row in data.rows} == {
        "Sur": 150.0,
        "Norte": 100.0,
    }


async def test_the_same_spec_recalculates_when_a_new_file_arrives(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)
    antes = await _render(container, enero.dataset.id, VENTAS_POR_REGION)

    await _ingest(container, FEBRERO, dataset_id=enero.dataset.id)
    despues = await _render(container, enero.dataset.id, VENTAS_POR_REGION)

    # Ni una llamada al LLM entre medias: solo la spec y los datos nuevos.
    assert {row["region"] for row in antes.rows} == {"Norte", "Sur"}
    assert {row["region"]: row["sum_valor"] for row in despues.rows} == {
        "Norte": 120.0,
        "Sur": 90.0,
        "Este": 60.0,
    }


async def test_a_spec_stays_valid_against_the_schema_of_the_new_file(
    container: Container,
) -> None:
    enero = await _ingest(container, ENERO)
    await _ingest(container, FEBRERO, dataset_id=enero.dataset.id)

    session = container.session_factory()
    try:
        stored: Dataset | None = await SqlAlchemyDatasetRepository(session).get(enero.dataset.id)
    finally:
        await session.close()

    assert stored is not None
    assert validate_spec(VENTAS_POR_REGION, stored.schema_) == ()


async def test_rendering_a_dataset_without_data_says_so(container: Container) -> None:
    # Un dataset solo existe tras una ingesta correcta, asi que se fuerza el
    # estado guardando uno sin version activa.
    session = container.session_factory()
    try:
        repository = SqlAlchemyDatasetRepository(session)
        enero = await _ingest(container, ENERO)
        vacio = Dataset(
            owner_id=OWNER,
            name="vacio",
            schema=enero.dataset.schema_,
        )
        await repository.add(vacio)
        await session.commit()
    finally:
        await session.close()

    with pytest.raises(DatasetHasNoDataError):
        await _render(container, vacio.id, VENTAS_POR_REGION)
