from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Instante actual, siempre con tzinfo.

    SQLite no guarda zona horaria; si dejamos entrar datetimes naive acabamos
    comparando manzanas con peras al ordenar versiones de un dataset.
    """
    return datetime.now(UTC)
