from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentcanvas.bootstrap.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def get_session(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    """Una sesion por peticion, cerrada pase lo que pase."""
    session = container.session_factory()
    try:
        yield session
    finally:
        await session.close()


def get_owner_id(container: Annotated[Container, Depends(get_container)]) -> str:
    """MVP monousuario.

    El dia que haya autenticacion, esta es la unica funcion que cambia: todo lo
    demas ya recibe el `owner_id` por parametro.
    """
    return container.settings.default_owner_id


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
OwnerDep = Annotated[str, Depends(get_owner_id)]
