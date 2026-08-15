# AgentCanvas AI — convenciones

Diseno completo en `AgentCanvas_AI.md`. Este archivo son las reglas de trabajo.

## Entorno

Conda, entorno `agentcanvas` (Python 3.12). En PowerShell 5.1 los comandos no se
encadenan con `&&`; van en lineas separadas o unidos por `;`.

```powershell
conda activate agentcanvas
pytest
ruff check src tests
mypy
```

Si conda no esta en el PATH de la terminal, el interprete del entorno funciona
igual sin activar nada:
`& "$env:USERPROFILE\anaconda3\envs\agentcanvas\python.exe" -m pytest`

Las libs con binarios pesados (pandas, pyarrow, openpyxl) van en `environment.yml`
desde conda-forge. El resto en `pyproject.toml`.

## Arquitectura hexagonal

Las dependencias apuntan hacia dentro:

- `domain/` — entidades y reglas puras. Solo stdlib y pydantic. Nada mas.
- `application/` — casos de uso y puertos (interfaces). Tampoco importa infraestructura.
- `infrastructure/` — adaptadores: OpenAI, SQLAlchemy, FastAPI, pandas, subproceso.
- `agent/` — harness del agente. Habla con el modelo solo via `LLMPort`.
- `bootstrap/` — unico lugar donde se ensambla todo.

`tests/test_architecture.py` hace cumplir esto. Si falla, el arreglo es mover el
codigo de capa, no relajar el test.

## Reglas que no se negocian

1. **El recalculo de visualizaciones no pasa por el LLM.** La `VisualSpec` la
   ejecuta un motor de queries determinista. El modelo solo crea o edita specs.
2. **Nunca ejecutar codigo generado dentro del proceso de FastAPI.** Siempre
   subproceso aislado, con cwd propio, env limpio, timeout y allowlist de imports
   validada por AST antes de ejecutar.
3. **El proveedor de IA no se filtra fuera de `infrastructure/llm`.** Un unico
   adaptador compatible con la API de OpenAI, parametrizado por `base_url` y
   `model`. Endpoint: `v1/chat/completions` (no Responses API) por portabilidad
   a vLLM. Salidas estructuradas por JSON schema, no por tool calling.
4. **`owner_id` en todas las entidades** desde el principio, aunque el MVP sea
   monousuario (`local-user`).
5. **Specs persistidas como JSON de un modelo pydantic**, via `TypeDecorator`,
   no como dict suelto: SQLite hoy, JSONB el dia que haga falta.
6. **Alembic desde el primer modelo.** Nada de borrar el `.db` para migrar.
7. **Archivos del usuario en `var/`**, que esta en `.gitignore`. Nunca se versionan.

## Tests

- El harness se testea con un `FakeLLM` de respuestas guionadas: cero coste y
  detecta regresiones al tocar prompts.
- El motor de queries se testea con datasets fixture: misma spec + archivo nuevo
  del mismo schema debe dar el resultado recalculado correcto.
