from __future__ import annotations

from typing import Protocol

from agentcanvas.domain.dataset.entities import Dataset, DatasetVersion, StoredFile


class UnitOfWorkPort(Protocol):
    """Frontera transaccional.

    Los casos de uso deciden cuando una operacion es atomica; el adaptador
    decide como. Sin esto, cada repositorio haria commit por su cuenta y una
    ingesta a medias dejaria un dataset sin version.
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class StoredFileRepositoryPort(Protocol):
    async def add(self, file: StoredFile) -> None: ...

    async def get(self, file_id: str) -> StoredFile | None: ...

    async def find_by_checksum(self, owner_id: str, checksum: str) -> StoredFile | None: ...


class DatasetRepositoryPort(Protocol):
    async def add(self, dataset: Dataset) -> None: ...

    async def update(self, dataset: Dataset) -> None: ...

    async def get(self, dataset_id: str) -> Dataset | None: ...

    async def list_for_owner(self, owner_id: str) -> list[Dataset]: ...

    async def find_compatible(self, owner_id: str, fingerprint: str) -> list[Dataset]:
        """Datasets del usuario cuyo schema coincide con esa huella.

        Es lo que permite ofrecer "este archivo encaja en el dataset Ventas,
        actualizo el dashboard?" en vez de crear un dataset huerfano cada mes.
        """
        ...

    async def add_version(self, version: DatasetVersion) -> None: ...

    async def get_version(self, version_id: str) -> DatasetVersion | None: ...

    async def list_versions(self, dataset_id: str) -> list[DatasetVersion]: ...
