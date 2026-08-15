# AgentCanvas AI

Un chat que entiende hojas de cálculo desordenadas y construye visualizaciones
que se actualizan solas.

Adjuntas un Excel, hablas con normalidad, y los gráficos aparecen dentro de la
conversación. Cuando llega el archivo del mes siguiente, los gráficos que
guardaste muestran los datos nuevos sin volver a pedirle nada al modelo.

> Estado: en desarrollo activo. Funciona de extremo a extremo y se ha probado
> contra archivos reales, pero no es un producto terminado. Al final del
> documento están las cosas que todavía no hace bien.

## Vídeo

<!-- Sube Demo.mp4 arrastrandolo a un comentario de issue en GitHub y pega
     aqui la URL https://github.com/user-attachments/assets/... que devuelve.
     Puesta a pelo en su propia linea, GitHub la convierte en un reproductor. -->

_(pendiente de subir)_

---

## El problema

Los archivos que la gente usa de verdad no son tablas. Uno de los ficheros con
los que se ha desarrollado esto tiene:

- **once hojas**, tres de ellas vacías;
- la cabecera en la **fila 3**, bajo un título en celdas combinadas;
- **346 columnas**;
- y una hoja con **nueve tablas puestas una al lado de otra**, cada una con sus
  propias fechas y cantidades, más filas de totales al pie.

Otro tiene diez filas de instrucciones antes de la cabecera y una fila de
ejemplo que dice literalmente «borra esta fila».

Cualquier lector que asuma «primera fila = cabeceras» produce basura con estos
archivos. Y lo hace en silencio, que es lo peor: sale una tabla con nombres de
columna raros y nadie se entera hasta que un gráfico da una cifra imposible.

## La idea

Dos principios sostienen el diseño.

**No se guardan resultados, se guarda la lógica que los produce.** Una
visualización guardada es una especificación declarativa: qué columna en cada
eje, qué agregación, qué filtros, qué orden. Los números no se almacenan en
ninguna parte; se recalculan cada vez que abres el panel. Por eso subir el
archivo del mes siguiente actualiza veinte gráficos a la vez sin gastar un
token.

Lo mismo con la extracción: se guarda **cómo** se recortó la tabla del archivo
—hoja, fila de cabecera, rango de columnas, filas descartadas— para poder
releer el archivo nuevo exactamente igual.

**El modelo propone, el dominio dispone.** El LLM nunca ejecuta nada. Produce
especificaciones que se validan contra el esquema real antes de tocar los
datos, y si algo no encaja se le devuelve el motivo para que se corrija. Un
modelo peor produce un gráfico peor elegido, nunca un panel roto.

## Lo que se puede ver

**El cálculo, en Python.** Cada gráfico lleva el código que lo produce:

```python
import pandas as pd

df = pd.read_parquet('datos.parquet')

# Agregacion
resultado = df.groupby(['species'], dropna=False, observed=True).agg(
    count_id=('id', 'count'),
).reset_index()

# Orden
resultado = resultado.sort_values('count_id', ascending=False, kind='stable')
```

No es una ilustración. Se genera a partir de la especificación, y hay once
tests que **ejecutan ese código y comparan el resultado con el del motor**,
fila a fila, para series agrupadas, filtros de fecha, filas sin agregar y
varias medidas a la vez. Si algún día divergieran, esos tests se ponen rojos.

**Lo que olió raro.** Una extracción puede terminar sin errores y aun así estar
mal. Cuando eso pasa, se dice:

```
La cabecera repite (fecha, semilla, cantidad) hasta 10 veces. Casi seguro son
10 tablas puestas una al lado de otra, no una sola: cada bloque de columnas es
una tabla distinta, y su identidad está en la fila de encima, no dentro de los
datos.

Hay 11 filas con 'fecha' vacío. Suelen ser totales o separadores, y falsean
cualquier suma o máximo.
```

Ese aviso va al modelo **y al usuario**, junto a las primeras filas de lo
extraído. Sin verlas, una extracción equivocada no se nota hasta dos preguntas
después, cuando ya es un gráfico.

## Arquitectura

Hexagonal, con las dependencias apuntando hacia dentro:

```
domain/          entidades y reglas puras (solo stdlib + pydantic)
application/     casos de uso y puertos
agent/           harness propio: bucle de herramientas, presupuesto, trazas
infrastructure/  OpenAI, SQLAlchemy, FastAPI, pandas, openpyxl
bootstrap/       único punto de ensamblaje
```

`tests/test_architecture.py` recorre por AST cada archivo de `domain`,
`application` y `agent` y falla si aparece un import de infraestructura. La
regla se hace cumplir sola, no por revisión.

**El harness es propio**, sin framework de agentes. Son unas 400 líneas: bucle
de herramientas, presupuesto explícito en iteraciones y tokens, ciclo de
corrección y traza de todos los intentos, incluidos los fallidos.

**El proveedor de IA está desacoplado.** Un único adaptador compatible con la
API de OpenAI, parametrizado por URL y modelo, con una tabla de capacidades por
modelo: si soporta JSON Schema, tool calling nativo o `reasoning_effort`, y qué
hacer cuando no. Cambiar a un modelo servido con vLLM son tres líneas del
`.env`.

## Puesta en marcha

Windows con PowerShell. Los comandos van uno por línea: PowerShell 5.1 no
admite `&&`.

```powershell
conda env create -f environment.yml
copy .env.example .env
```

Hay que poner una clave de OpenAI en `LLM_API_KEY`. Después:

```powershell
$env:USERPROFILE\anaconda3\envs\agentcanvas\python.exe -m alembic upgrade head
$env:USERPROFILE\anaconda3\envs\agentcanvas\python.exe -m pytest -q
```

Dos terminales para levantarlo:

```powershell
$env:USERPROFILE\anaconda3\envs\agentcanvas\python.exe -m uvicorn agentcanvas.main:app --reload
```

```powershell
npm run dev --prefix frontend
```

La aplicación queda en http://localhost:5173 y la documentación de la API en
http://127.0.0.1:8000/docs

## Coste

Con `gpt-5.6-luna` y buena parte de la entrada en caché:

| | |
|---|---|
| Un gráfico sobre datos ya preparados | ~$0.0004 |
| Explorar un libro de once hojas y preguntar | ~$0.001 |
| Una conversación completa de cuatro turnos | ~$0.005 |
| **Actualizar con el archivo del mes siguiente** | **$0** |

Lo último no es una errata: releer y recalcular no pasa por el modelo.

## Lo que todavía no hace bien

- **Hojas con varios bloques de tablas.** Se avisa de que están ahí, pero el
  agente todavía elige mal las coordenadas más veces de las que debería. Es el
  caso más difícil y el siguiente en la lista.
- **No amplía lo ya preparado.** Si preparó cuatro columnas y le pides algo que
  necesita una quinta, a veces dice que no puede en vez de volver a preparar.
- **No hay automatizaciones.** Generar y ejecutar Python en un sandbox —la otra
  mitad del diseño original— está sin empezar.
- **Un solo usuario.** Sin autenticación. `owner_id` existe en el modelo de
  datos desde el principio, así que añadirla no obliga a migrar nada.
- Solo CSV y XLSX. PDF y DOCX, pendientes.

## Números

| | |
|---|---|
| Backend | ~6.700 líneas |
| Tests | ~3.750 líneas, 272 tests |
| Frontend | ~2.100 líneas |
| Comprobación de tipos | `mypy --strict`, 96 archivos |

## Stack

Python 3.12 · FastAPI · SQLAlchemy · SQLite · pandas · openpyxl · Alembic ·
pydantic · React · TypeScript · Vite · Tailwind · ECharts
