from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from agentcanvas.bootstrap.container import Container, build_container
from agentcanvas.config import Settings
from agentcanvas.infrastructure.persistence.models import Base
from tests.fakes import FakeLLM

OWNER = "test-owner"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # data_dir en tmp: la SQLite y los archivos quedan aislados por test.
    return Settings(_env_file=None, data_dir=tmp_path / "var")  # type: ignore[call-arg]


@pytest.fixture
def llm() -> FakeLLM:
    """Ningun test toca la red ni la cuota: el modelo va siempre guionado."""
    return FakeLLM()


@pytest.fixture
async def container(settings: Settings, llm: FakeLLM) -> AsyncIterator[Container]:
    built = build_container(settings, llm=llm)
    async with built.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield built
    await built.engine.dispose()


def csv_bytes(rows: str, *, encoding: str = "utf-8") -> bytes:
    return rows.strip().encode(encoding)


def xlsx_bytes(data: dict[str, list[Any]], destination: Path) -> bytes:
    import pandas as pd

    pd.DataFrame(data).to_excel(destination, index=False, engine="openpyxl")
    return destination.read_bytes()
