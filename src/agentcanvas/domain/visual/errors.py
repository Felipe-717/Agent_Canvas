from __future__ import annotations

from agentcanvas.domain.shared.errors import DomainError


class InvalidVisualSpecError(DomainError):
    """La spec no encaja con el dataset o es incoherente consigo misma.

    El mensaje esta escrito para que se le pueda devolver literalmente al
    modelo en el ciclo de correccion: dice que esta mal y que columnas hay
    disponibles, no "validation failed".
    """

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("La visualizacion no es valida:\n- " + "\n- ".join(problems))
        self.problems = problems
