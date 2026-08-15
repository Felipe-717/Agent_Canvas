"""Puertos: las interfaces que la infraestructura debe implementar.

Implementados en Fase 1:
    FileStoragePort   -> infrastructure.storage (disco local)
    TabularReaderPort -> infrastructure.tabular (pandas)
    *RepositoryPort   -> infrastructure.persistence (SQLAlchemy)

Previstos:
    LLMPort           -> infrastructure.llm (compatible con la API de OpenAI)
    CodeExecutorPort  -> infrastructure.execution (subproceso aislado)
    QueryEnginePort   -> infrastructure.query (compila VisualSpec a agregaciones)
"""

from agentcanvas.application.ports.repositories import (
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.tabular import NormalizedTable, TabularReaderPort

__all__ = [
    "DatasetRepositoryPort",
    "FileStoragePort",
    "NormalizedTable",
    "StoredFileRepositoryPort",
    "TabularReaderPort",
    "UnitOfWorkPort",
]
