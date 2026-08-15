"""Unico punto donde se ensambla el sistema.

Que los adaptadores se asignen aqui a variables tipadas como puertos no es
decorativo: es lo que hace que mypy verifique que cada adaptador cumple su
Protocol. Si `PandasQueryEngine` deja de encajar en `QueryEnginePort`, falla la
comprobacion de tipos, no la aplicacion en produccion.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentcanvas.application.ports.llm import LLMPort
from agentcanvas.application.ports.query import QueryEnginePort
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.workbook import WorkbookReaderPort
from agentcanvas.application.use_cases.chat import ChatService
from agentcanvas.application.use_cases.dashboards import DashboardService
from agentcanvas.application.use_cases.refresh import RefreshDatasetUseCase
from agentcanvas.config import Settings, get_settings
from agentcanvas.infrastructure.llm.factory import build_llm
from agentcanvas.infrastructure.persistence.conversations import (
    SqlAlchemyConversationRepository,
)
from agentcanvas.infrastructure.persistence.dashboards import SqlAlchemyDashboardRepository
from agentcanvas.infrastructure.persistence.repositories import (
    SqlAlchemyDatasetRepository,
    SqlAlchemyStoredFileRepository,
    SqlAlchemyUnitOfWork,
)
from agentcanvas.infrastructure.persistence.session import build_engine, build_session_factory
from agentcanvas.infrastructure.query.pandas_engine import PandasQueryEngine
from agentcanvas.infrastructure.storage.local_file_storage import LocalFileStorage
from agentcanvas.infrastructure.tabular.workbook_reader import OpenpyxlWorkbookReader


@dataclass(frozen=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    query_engine: QueryEnginePort
    workbook: WorkbookReaderPort
    llm: LLMPort

    def chat(self, session: AsyncSession) -> ChatService:
        return ChatService(
            llm=self.llm,
            conversations=SqlAlchemyConversationRepository(session),
            datasets=SqlAlchemyDatasetRepository(session),
            files=SqlAlchemyStoredFileRepository(session),
            storage=self.storage,
            workbook=self.workbook,
            engine=self.query_engine,
            uow=SqlAlchemyUnitOfWork(session),
        )

    def refresh_dataset(self, session: AsyncSession) -> RefreshDatasetUseCase:
        return RefreshDatasetUseCase(
            datasets=SqlAlchemyDatasetRepository(session),
            files=SqlAlchemyStoredFileRepository(session),
            storage=self.storage,
            workbook=self.workbook,
            uow=SqlAlchemyUnitOfWork(session),
        )

    def dashboards(self, session: AsyncSession) -> DashboardService:
        return DashboardService(
            dashboards=SqlAlchemyDashboardRepository(session),
            datasets=SqlAlchemyDatasetRepository(session),
            storage=self.storage,
            engine=self.query_engine,
            uow=SqlAlchemyUnitOfWork(session),
        )


def build_container(settings: Settings | None = None, *, llm: LLMPort | None = None) -> Container:
    """`llm` se inyecta en los tests para no tocar la red ni la cuota."""
    resolved = settings or get_settings()
    resolved.ensure_directories()
    engine = build_engine(resolved.database_url, echo=resolved.debug)
    storage: FileStoragePort = LocalFileStorage(resolved.data_dir)
    query_engine: QueryEnginePort = PandasQueryEngine()
    return Container(
        settings=resolved,
        engine=engine,
        session_factory=build_session_factory(engine),
        storage=storage,
        query_engine=query_engine,
        workbook=OpenpyxlWorkbookReader(),
        llm=llm or build_llm(resolved),
    )
