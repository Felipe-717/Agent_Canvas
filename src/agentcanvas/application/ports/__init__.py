"""Puertos: las interfaces que la infraestructura debe implementar.

Implementados:
    FileStoragePort   -> infrastructure.storage (disco local)
    TabularReaderPort -> infrastructure.tabular (pandas)
    *RepositoryPort   -> infrastructure.persistence (SQLAlchemy)
    QueryEnginePort   -> infrastructure.query (compila VisualSpec a agregaciones)
    LLMPort           -> infrastructure.llm (compatible con la API de OpenAI)

Previstos:
    CodeExecutorPort  -> infrastructure.execution (subproceso aislado)
"""

from agentcanvas.application.ports.llm import (
    LLMError,
    LLMPort,
    LLMProtocolError,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
    Message,
    ResponseFormat,
    Role,
    ToolCall,
    ToolDefinition,
    Usage,
)
from agentcanvas.application.ports.query import QueryEnginePort
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
    "LLMError",
    "LLMPort",
    "LLMProtocolError",
    "LLMRequest",
    "LLMResponse",
    "LLMUnavailableError",
    "Message",
    "NormalizedTable",
    "QueryEnginePort",
    "ResponseFormat",
    "Role",
    "StoredFileRepositoryPort",
    "TabularReaderPort",
    "ToolCall",
    "ToolDefinition",
    "UnitOfWorkPort",
    "Usage",
]
