"""Puertos: las interfaces que la infraestructura debe implementar.

Previstos:
    LLMPort           -> infrastructure.llm (compatible con la API de OpenAI)
    CodeExecutorPort  -> infrastructure.execution (subproceso aislado)
    QueryEnginePort   -> infrastructure.query (compila VisualSpec a agregaciones)
    FileStoragePort   -> infrastructure.storage
    *RepositoryPort   -> infrastructure.persistence
"""
