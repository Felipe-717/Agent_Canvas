from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Id legible con prefijo: `ds_3f2a...`, `file_9c1b...`.

    El prefijo hace que un id suelto en un log o en un error sea identificable
    sin tener que buscar de que tabla salio.
    """
    return f"{prefix}_{uuid4().hex}"
