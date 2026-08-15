"""Errores de dominio.

Son excepciones con significado de negocio: la capa web las traduce a codigos
HTTP y a mensajes accionables para el usuario. Nunca dejar que una excepcion de
pandas o de SQLAlchemy llegue al usuario tal cual.
"""

from __future__ import annotations


class DomainError(Exception):
    """Raiz de todos los errores de negocio."""


class NotFoundError(DomainError):
    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__(f"No existe {entity} con id {entity_id}")
        self.entity = entity
        self.entity_id = entity_id


class UnsupportedFileTypeError(DomainError):
    def __init__(self, filename: str, supported: tuple[str, ...]) -> None:
        super().__init__(
            f"El archivo '{filename}' no tiene un formato soportado. "
            f"Formatos aceptados: {', '.join(supported)}"
        )
        self.filename = filename
        self.supported = supported


class EmptyFileError(DomainError):
    def __init__(self, filename: str) -> None:
        super().__init__(f"El archivo '{filename}' no contiene filas de datos")
        self.filename = filename
