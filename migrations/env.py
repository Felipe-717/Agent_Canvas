from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from agentcanvas.config import get_settings
from agentcanvas.infrastructure.persistence.models import Base
from agentcanvas.infrastructure.persistence.types import PydanticJSON

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Por defecto la URL sale de la configuracion de la app, no del .ini: una sola
# fuente de verdad. Pero si quien invoca ya fijo una URL (los tests apuntando a
# una base temporal), esa manda: si no, cada test migraria la base de desarrollo.
if not config.get_main_option("sqlalchemy.url", default=None):
    settings = get_settings()
    settings.ensure_directories()  # SQLite no crea el directorio que la contiene
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """`PydanticJSON` es un JSON a efectos de DDL.

    Sin esto, alembic escribe en la migracion una referencia al tipo de la
    aplicacion: la migracion dejaria de aplicarse el dia que ese codigo cambie
    de sitio, y una migracion no debe depender del codigo vivo.
    """
    if type_ == "type" and isinstance(obj, PydanticJSON):
        return "sa.JSON()"
    return False


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=_render_item,
        # SQLite no sabe hacer ALTER de casi nada: sin batch mode, cualquier
        # migracion que toque una columna existente falla.
        render_as_batch=True,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from agentcanvas.infrastructure.persistence.session import build_engine

    engine = build_engine(config.get_main_option("sqlalchemy.url") or "")
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
