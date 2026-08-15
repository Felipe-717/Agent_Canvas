"""La migracion debe poder aplicarse desde cero sobre una base vacia.

Sin este test, el `.db` de desarrollo sigue funcionando por inercia mientras las
migraciones se pudren en silencio.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from agentcanvas.config import PROJECT_ROOT, Settings
from agentcanvas.infrastructure.persistence.models import Base
from agentcanvas.infrastructure.persistence.session import build_engine

EXPECTED_TABLES = {"datasets", "dataset_versions", "stored_files"}


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def test_upgrade_head_creates_every_table(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "var")  # type: ignore[call-arg]
    settings.ensure_directories()

    command.upgrade(_alembic_config(settings), "head")

    async def _tables() -> set[str]:
        engine = build_engine(settings.database_url)
        try:
            async with engine.connect() as connection:
                names = await connection.run_sync(
                    lambda sync_conn: set(inspect(sync_conn).get_table_names())
                )
            return names
        finally:
            await engine.dispose()

    tables = asyncio.run(_tables())
    assert tables >= EXPECTED_TABLES
    assert "alembic_version" in tables


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_the_orm_metadata_declares_the_expected_tables(table: str) -> None:
    # Detecta que alguien anada un modelo y olvide generar la migracion:
    # este test y el anterior tienen que hablar de las mismas tablas.
    assert table in Base.metadata.tables
