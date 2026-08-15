from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileStoragePort(Protocol):
    """Almacenamiento de binarios. Hoy disco local, manana S3."""

    def save(self, content: bytes, *, key: str) -> str:
        """Guarda el contenido bajo `key` y devuelve la clave definitiva."""
        ...

    def path_for(self, key: str) -> Path:
        """Ruta local de una clave.

        Existe porque pandas y el subproceso de ejecucion necesitan un path
        real. Un adaptador remoto tendria que materializar el archivo en un
        cache local para cumplirlo.
        """
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...
