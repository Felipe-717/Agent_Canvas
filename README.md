# AgentCanvas AI

Plataforma de automatizacion de datos y BI generativo. El usuario carga un Excel
o CSV, describe en lenguaje natural lo que quiere, y un agente construye la
automatizacion o la visualizacion. Al subir el archivo del mes siguiente, todo se
recalcula solo.

El diseno completo esta en [AgentCanvas_AI.md](AgentCanvas_AI.md).

## Principio de diseno

El sistema no guarda resultados, guarda **la logica para reproducirlos**: schema
de entrada + instruccion + pipeline + validacion. Por eso el recalculo de una
visualizacion **no pasa por el LLM**: la `VisualSpec` la ejecuta un motor de
queries determinista. El modelo solo interviene al crear o editar la spec.

## Arquitectura

Hexagonal. Las dependencias apuntan hacia dentro, siempre:

```
domain/          entidades y reglas puras (solo stdlib + pydantic)
application/     casos de uso + puertos (interfaces)
infrastructure/  adaptadores: OpenAI, SQLAlchemy, FastAPI, pandas, subproceso
agent/           harness propio del agente (bucle, tools, presupuesto, trazas)
bootstrap/       unico punto donde se ensambla todo
```

`tests/test_architecture.py` verifica esta regla automaticamente.

## Estado

- **Fase 0** — entorno conda, configuracion, esqueleto hexagonal.
- **Fase 1** — dominio de datasets, ingesta de CSV/XLSX con deteccion de schema,
  huella de compatibilidad, persistencia SQLite y migraciones.
- **Fase 2** — `VisualSpec` tipada, validacion contra el schema y motor de
  queries determinista.
- **Fase 3** — puerto del modelo, adaptador compatible con OpenAI, harness con
  presupuesto y ciclo de correccion, y el agente de visualizaciones.
- **Fase 4** — API HTTP con FastAPI y streaming SSE del agente.

Lo que ya funciona: subir un CSV o Excel crea un `Dataset` cuyo schema queda como
contrato; subir despues un archivo del mismo schema crea una version nueva y
actualiza el dataset; uno incompatible se rechaza diciendo que columna falta. Una
`VisualSpec` guardada se ejecuta contra la version activa, de modo que el mismo
grafico se recalcula solo al llegar datos nuevos.

## Puesta en marcha

Los comandos van uno por linea a proposito: PowerShell 5.1, que es el que trae
Windows por defecto, no admite `&&` para encadenar.

```powershell
conda env create -f environment.yml
conda activate agentcanvas
copy .env.example .env
alembic upgrade head
pytest
```

Falta poner la clave de OpenAI en `LLM_API_KEY` dentro del `.env`.

Si `conda activate` responde que no reconoce el comando, es que conda no esta en
el PATH de esa terminal. Se arregla de una vez con `conda init powershell` y
abriendo una terminal nueva, o se evita usando el interprete del entorno
directamente:

```powershell
& "$env:USERPROFILE\anaconda3\envs\agentcanvas\python.exe" -m uvicorn agentcanvas.main:app --reload
```

### Levantar la aplicacion

Hacen falta dos terminales. La primera, la API:

```powershell
uvicorn agentcanvas.main:app --reload
```

La segunda, el frontend:

```powershell
npm run dev --prefix frontend
```

La aplicacion queda en http://localhost:5173 y la documentacion interactiva de
la API en http://127.0.0.1:8000/docs

### Probar el modelo real

Es lo unico del repositorio que gasta cuota. Alrededor de $0.0004 por peticion.

```powershell
python scripts/smoke_visual.py "top 3 productos por venta"
```

## Modelo de IA

Arranca con la API de OpenAI (`gpt-5.6-luna`) usando **`v1/chat/completions`**,
no la Responses API: es el endpoint que vLLM implementa de forma estable. Las
salidas estructuradas se piden por JSON schema, no por tool calling, por el mismo
motivo.

Cambiar a un modelo open-source servido con vLLM son tres lineas del `.env`
(`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Ninguna otra parte del codigo
conoce al proveedor.
