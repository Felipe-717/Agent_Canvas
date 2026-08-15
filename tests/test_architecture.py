"""La regla hexagonal, verificada por un test en vez de por buena voluntad.

Si alguien importa SQLAlchemy en el dominio, esto falla en CI, no en la revision.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "agentcanvas"

# Paquetes de terceros que no pueden aparecer en las capas puras.
FORBIDDEN_THIRD_PARTY = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "openai",
    "pandas",
    "pyarrow",
    "openpyxl",
    "httpx",
    "uvicorn",
}

PURE_LAYERS = ("domain", "application")


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        # `from . import x` (level > 0) es relativo: no aporta raiz externa.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _full_module_targets(path: Path) -> set[str]:
    """Modulos absolutos importados, para detectar agentcanvas.infrastructure.*"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            targets.add(node.module)
    return targets


def _pure_layer_files() -> list[Path]:
    return [p for layer in PURE_LAYERS for p in (SRC / layer).rglob("*.py")]


@pytest.mark.parametrize("path", _pure_layer_files(), ids=lambda p: str(p.name))
def test_pure_layers_do_not_import_third_party_infrastructure(path: Path) -> None:
    offenders = _imported_roots(path) & FORBIDDEN_THIRD_PARTY
    assert not offenders, f"{path.relative_to(SRC)} importa {sorted(offenders)}"


@pytest.mark.parametrize("path", _pure_layer_files(), ids=lambda p: str(p.name))
def test_pure_layers_do_not_import_infrastructure(path: Path) -> None:
    offenders = {
        module
        for module in _full_module_targets(path)
        if module.startswith(("agentcanvas.infrastructure", "agentcanvas.bootstrap"))
    }
    assert not offenders, f"{path.relative_to(SRC)} importa {sorted(offenders)}"


def test_domain_does_not_import_application() -> None:
    offenders: dict[str, set[str]] = {}
    for path in (SRC / "domain").rglob("*.py"):
        bad = {m for m in _full_module_targets(path) if m.startswith("agentcanvas.application")}
        if bad:
            offenders[str(path.relative_to(SRC))] = bad
    assert not offenders, f"El dominio no puede depender de la aplicacion: {offenders}"
