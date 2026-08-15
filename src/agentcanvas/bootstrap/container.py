"""Unico punto donde se ensambla el sistema.

Que los adaptadores se asignen aqui a variables tipadas como puertos no es
decorativo: es lo que hace que mypy verifique que cada adaptador cumple su
Protocol. Si `PandasTabularReader` deja de encajar en `TabularReaderPort`, falla
la comprobacion de tipos, no la aplicacion en produccion.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentcanvas.application.ports.repositories import (
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.tabular import TabularReaderPort
from agentcanvas.application.use_cases.ingest_file import IngestFileUseCase
from agentcanvas.config import Settings, get_settings
from agentcanvas.infrastructure.persistence.repositories import (
    SqlAlchemyDatasetRepository,
    SqlAlchemyStoredFileRepository,
    SqlAlchemyUnitOfWork,
)
from agentcanvas.infrastructure.persistence.session import build_engine, build_session_factory
from agentcanvas.infrastructure.storage.local_file_storage import LocalFileStorage
from agentcanvas.infrastructure.tabular.pandas_reader import PandasTabularReader


@dataclass(frozen=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    reader: TabularReaderPort

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


def build_container(settings: Settings | None = None) -> Container:
    resolved = settings or get_settings()
    resolved.ensure_directories()
    engine = build_engine(resolved.database_url, echo=resolved.debug)
    storage: FileStoragePort = LocalFileStorage(resolved.data_dir)
    reader: TabularReaderPort = PandasTabularReader()
    return Container(
        settings=resolved,
        engine=engine,
        session_factory=build_session_factory(engine),
        storage=storage,
        reader=reader,
    )
