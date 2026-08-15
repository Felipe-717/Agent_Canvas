"""Dashboard y visuales guardados.

Un dashboard no almacena numeros. Almacena, por cada visual, el dataset del que
sale, la especificacion que lo produce y donde va colocado. Los valores se
recalculan cada vez que se abre, de modo que subir el archivo del mes siguiente
actualiza el tablero entero sin tocar nada mas.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agentcanvas.domain.shared.clock import utcnow
from agentcanvas.domain.shared.identifiers import new_id
from agentcanvas.domain.visual.spec import VisualSpec

GRID_COLUMNS = 12
"""Ancho de la rejilla. El frontend usa el mismo numero; es parte del contrato."""


class Placement(BaseModel):
    """Posicion y tamano en la rejilla, en columnas y filas."""

    model_config = ConfigDict(frozen=True)

    x: int = Field(default=0, ge=0, lt=GRID_COLUMNS)
    y: int = Field(default=0, ge=0)
    width: int = Field(default=6, ge=1, le=GRID_COLUMNS)
    height: int = Field(default=6, ge=2)

    def clamped(self) -> Placement:
        """Recorta el bloque para que no se salga de la rejilla.

        El frontend puede mandar una posicion invalida tras un arrastre raro, y
        un visual fuera de la rejilla es un visual que el usuario no puede
        recuperar.
        """
        width = min(self.width, GRID_COLUMNS)
        x = min(self.x, GRID_COLUMNS - width)
        return Placement(x=max(x, 0), y=self.y, width=width, height=self.height)


class Visual(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: new_id("vis"))
    dashboard_id: str
    dataset_id: str
    spec: VisualSpec
    placement: Placement = Placement()
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def title(self) -> str:
        return self.spec.title

    def moved_to(self, placement: Placement) -> Visual:
        return self.model_copy(update={"placement": placement.clamped(), "updated_at": utcnow()})

    def with_spec(self, spec: VisualSpec) -> Visual:
        return self.model_copy(update={"spec": spec, "updated_at": utcnow()})


class Dashboard(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: new_id("dash"))
    owner_id: str
    name: str = "Sin titulo"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def next_placement(self, existing: tuple[Visual, ...]) -> Placement:
        """Donde cae un visual nuevo: debajo de todo, a media anchura.

        Colocarlo al final y no en el primer hueco libre es deliberado: el
        usuario acaba de pedirlo, y esperar verlo aparecer donde mira.
        """
        bottom = max((v.placement.y + v.placement.height for v in existing), default=0)
        return Placement(x=0, y=bottom, width=6, height=6)
