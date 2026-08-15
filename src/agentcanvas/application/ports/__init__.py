"""Puertos: las interfaces que la infraestructura debe implementar.

Implementados:
    FileStoragePort          -> infrastructure.storage (disco local)
    WorkbookReaderPort       -> infrastructure.tabular (openpyxl)
    QueryEnginePort          -> infrastructure.query (compila VisualSpec a agregaciones)
    LLMPort                  -> infrastructure.llm (compatible con la API de OpenAI)
    *RepositoryPort          -> infrastructure.persistence (SQLAlchemy)

Previstos:
    CodeExecutorPort         -> infrastructure.execution (subproceso aislado)
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
    ConversationRepositoryPort,
    DashboardRepositoryPort,
    DatasetRepositoryPort,
    StoredFileRepositoryPort,
    UnitOfWorkPort,
)
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.ports.tabular import NormalizedTable
from agentcanvas.application.ports.workbook import WorkbookReaderPort

__all__ = [
    "ConversationRepositoryPort",
    "DashboardRepositoryPort",
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
    "ToolCall",
    "ToolDefinition",
    "UnitOfWorkPort",
    "Usage",
    "WorkbookReaderPort",
]
