from __future__ import annotations

from agentcanvas.domain.dataset.schema import SchemaCompatibility
from agentcanvas.domain.shared.errors import DomainError


class DatasetHasNoDataError(DomainError):
    def __init__(self, dataset_name: str) -> None:
        super().__init__(f"El conjunto de datos '{dataset_name}' todavia no tiene datos")
        self.dataset_name = dataset_name


class SchemaMismatchError(DomainError):
    """El archivo nuevo no encaja en el contrato del dataset."""

    def __init__(self, dataset_name: str, compatibility: SchemaCompatibility) -> None:
        super().__init__(compatibility.explain())
        self.dataset_name = dataset_name
        self.compatibility = compatibility
