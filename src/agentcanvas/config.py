"""Configuracion del proceso.

Todo lo que ata AgentCanvas a un proveedor concreto vive aqui y en ningun otro
sitio: cambiar de OpenAI a un modelo servido con vLLM debe ser cambiar
`LLM_BASE_URL` y `LLM_MODEL` en el `.env`, nada mas.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]

# Raiz del repositorio: este archivo esta en src/agentcanvas/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicacion -----------------------------------------------------
    app_name: str = "AgentCanvas AI"
    debug: bool = False

    # MVP monousuario: no hay tabla User ni login, pero las entidades ya
    # llevan owner_id para que anadir multiusuario no sea una migracion total.
    default_owner_id: str = "local-user"

    # --- Almacenamiento -------------------------------------------------
    # var/ esta en .gitignore; nunca se versionan archivos del usuario.
    data_dir: Path = PROJECT_ROOT / "var"
    database_url: str = ""
    """Vacio = SQLite dentro de `data_dir`. Se resuelve a ruta absoluta para
    que alembic y la app apunten a la misma base sin depender del cwd."""

    # --- LLM ------------------------------------------------------------
    # Cualquier servidor compatible con la API de OpenAI: la API oficial o
    # vLLM (`vllm serve <modelo> --port 8000` -> http://host:8000/v1).
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-5.6-luna"
    llm_reasoning_effort: ReasoningEffort = "low"
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2

    # Rol separado para generar Python: es la tarea que mas capacidad exige,
    # asi que puede apuntar a un modelo distinto. Vacio = usa el modelo base.
    llm_codegen_model: str = ""
    llm_codegen_reasoning_effort: ReasoningEffort = "high"

    # --- Harness del agente ---------------------------------------------
    agent_max_iterations: int = 8
    agent_max_repair_attempts: int = 3

    # --- Ejecucion de codigo generado -----------------------------------
    execution_timeout_seconds: float = 60.0
    execution_max_output_bytes: int = 1_000_000

    @field_validator("llm_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _resolve_database_url(self) -> Settings:
        if not self.database_url:
            path = (self.data_dir / "agentcanvas.db").resolve()
            # SQLAlchemy quiere separadores POSIX incluso en Windows.
            self.database_url = f"sqlite+aiosqlite:///{path.as_posix()}"
        return self

    @property
    def codegen_model(self) -> str:
        return self.llm_codegen_model or self.llm_model

    @property
    def uploads_dir(self) -> Path:
        """Archivos originales subidos por el usuario. Inmutables."""
        return self.data_dir / "uploads"

    @property
    def datasets_dir(self) -> Path:
        """Datasets normalizados (Parquet) derivados de los originales."""
        return self.data_dir / "datasets"

    @property
    def runs_dir(self) -> Path:
        """Workspace aislado de cada ejecucion de codigo generado."""
        return self.data_dir / "runs"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.datasets_dir, self.runs_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
