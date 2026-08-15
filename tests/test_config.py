from __future__ import annotations

from pathlib import Path
from typing import Any

from agentcanvas.config import Settings


def _settings(**overrides: Any) -> Settings:
    # _env_file=None aisla el test de un .env real presente en la maquina.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults_point_to_openai_with_the_chosen_model() -> None:
    settings = _settings()
    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.llm_model == "gpt-5.6-luna"


def test_base_url_trailing_slash_is_normalised() -> None:
    settings = _settings(llm_base_url="http://localhost:8000/v1/")
    assert settings.llm_base_url == "http://localhost:8000/v1"


def test_codegen_model_falls_back_to_the_base_model() -> None:
    assert _settings().codegen_model == "gpt-5.6-luna"
    assert _settings(llm_codegen_model="gpt-5.6-sol").codegen_model == "gpt-5.6-sol"


def test_storage_paths_hang_off_the_data_dir(tmp_path: Path) -> None:
    settings = _settings(data_dir=tmp_path)
    assert settings.uploads_dir == tmp_path / "uploads"
    assert settings.datasets_dir == tmp_path / "datasets"
    assert settings.runs_dir == tmp_path / "runs"


def test_ensure_directories_is_idempotent(tmp_path: Path) -> None:
    settings = _settings(data_dir=tmp_path / "var")
    settings.ensure_directories()
    settings.ensure_directories()
    assert settings.uploads_dir.is_dir()
    assert settings.runs_dir.is_dir()
