from __future__ import annotations

from pathlib import Path


class LocalFileStorage:
    """Almacenamiento en disco bajo una raiz. Implementa `FileStoragePort`.

    Las claves son rutas relativas (`uploads/file_x.csv`). Se validan siempre
    contra la raiz: una clave con `..` no puede escapar del directorio de datos,
    y esa garantia importa porque parte de las claves acabaran derivando de
    nombres de archivo elegidos por el usuario.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            raise ValueError(f"La clave '{key}' apunta fuera del almacenamiento")
        return candidate

    def save(self, content: bytes, *, key: str) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return key

    def path_for(self, key: str) -> Path:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)
