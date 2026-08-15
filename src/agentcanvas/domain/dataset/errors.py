from __future__ import annotations

from agentcanvas.domain.dataset.schema import SchemaCompatibility
from agentcanvas.domain.shared.errors import DomainError


class SchemaMismatchError(DomainError):
    """El archivo nuevo no encaja en el contrato del dataset."""

    def __init__(self, dataset_name: str, compatibility: SchemaCompatibility) -> None:
        super().__init__(compatibility.explain())
        self.dataset_name = dataset_name
        self.compatibility = compatibility
