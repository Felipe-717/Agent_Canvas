"""Punto de entrada para uvicorn.

    uvicorn agentcanvas.main:app --reload
"""

from __future__ import annotations

from agentcanvas.infrastructure.web.app import create_app

app = create_app()
