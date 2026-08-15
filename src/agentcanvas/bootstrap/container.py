"""Unico punto donde se ensambla el sistema.

Que los adaptadores se asignen aqui a variables tipadas como puertos no es
decorativo: es lo que hace que mypy verifique que cada adaptador cumple su
Protocol. Si `PandasTabularReader` deja de encajar en `TabularReaderPort`, falla
la comprobacion de tipos, no la aplicacion en produccion.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentcanvas.agent.budget import Budget
from agentcanvas.agent.structured import StructuredGenerator
from agentcanvas.agent.visual_agent import VisualSpecAgent
from agentcanvas.application.ports.llm import LLMPort
from agentcanvas.application.ports.query import DatasetSamplerPort, QueryEnginePort
from agentcanvas.application.ports.repositories import (
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.tabular import TabularReaderPort
from agentcanvas.application.use_cases.create_visual import CreateVisualUseCase
from agentcanvas.application.use_cases.dashboards import DashboardService
from agentcanvas.application.use_cases.ingest_file import IngestFileUseCase
from agentcanvas.application.use_cases.render_visual import RenderVisualUseCase
from agentcanvas.config import Settings, get_settings
from agentcanvas.infrastructure.llm.factory import build_llm
from agentcanvas.infrastructure.persistence.dashboards import SqlAlchemyDashboardRepository
from agentcanvas.infrastructure.persistence.repositories import (
    SqlAlchemyDatasetRepository,
    SqlAlchemyStoredFileRepository,
    SqlAlchemyUnitOfWork,
)
from agentcanvas.infrastructure.persistence.session import build_engine, build_session_factory
from agentcanvas.infrastructure.query.pandas_engine import PandasQueryEngine
from agentcanvas.infrastructure.storage.local_file_storage import LocalFileStorage
from agentcanvas.infrastructure.tabular.pandas_reader import PandasTabularReader


@dataclass(frozen=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    reader: TabularReaderPort
    query_engine: QueryEnginePort
    sampler: DatasetSamplerPort
    llm: LLMPort

    def dashboards(self, session: AsyncSession) -> DashboardService:
        return DashboardService(
            dashboards=SqlAlchemyDashboardRepository(session),
            datasets=SqlAlchemyDatasetRepository(session),
            storage=self.storage,
            engine=self.query_engine,
            uow=SqlAlchemyUnitOfWork(session),
        )

    def create_visual(self, session: AsyncSession) -> CreateVisualUseCase:
        datasets: DatasetRepositoryPort = SqlAlchemyDatasetRepository(session)
        budget = Budget(max_iterations=self.settings.agent_max_repair_attempts + 1)
        return CreateVisualUseCase(
            datasets=datasets,
            storage=self.storage,
            engine=self.query_engine,
            sampler=self.sampler,
            agent=VisualSpecAgent(StructuredGenerator(self.llm, budget)),
        )

    def render_visual(self, session: AsyncSession) -> RenderVisualUseCase:
        datasets: DatasetRepositoryPort = SqlAlchemyDatasetRepository(session)
        return RenderVisualUseCase(
            datasets=datasets,
            storage=self.storage,
            engine=self.query_engine,
        )

    def ingest_file(self, session: AsyncSession) -> IngestFileUseCase:
        files: StoredFileRepositoryPort = SqlAlchemyStoredFileRepository(session)
        datasets: DatasetRepositoryPort = SqlAlchemyDatasetRepository(session)
        uow: UnitOfWorkPort = SqlAlchemyUnitOfWork(session)
        return IngestFileUseCase(
            storage=self.storage,
            reader=self.reader,
            files=files,
            datasets=datasets,
            uow=uow,
        )


def build_container(settings: Settings | None = None, *, llm: LLMPort | None = None) -> Container:
    """`llm` se inyecta en los tests para no tocar la red ni la cuota."""
    resolved = settings or get_settings()
    resolved.ensure_directories()
    engine = build_engine(resolved.database_url, echo=resolved.debug)
    storage: FileStoragePort = LocalFileStorage(resolved.data_dir)
    reader: TabularReaderPort = PandasTabularReader()
    pandas_engine = PandasQueryEngine()
    query_engine: QueryEnginePort = pandas_engine
    sampler: DatasetSamplerPort = pandas_engine
    return Container(
        settings=resolved,
        engine=engine,
        session_factory=build_session_factory(engine),
        storage=storage,
        reader=reader,
        query_engine=query_engine,
        sampler=sampler,
        llm=llm or build_llm(resolved),
    )
