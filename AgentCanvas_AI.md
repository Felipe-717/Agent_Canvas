# AgentCanvas AI

Plataforma fullstack de automatización y análisis de datos mediante agentes de IA.

El usuario carga archivos, describe en lenguaje natural qué necesita hacer y un agente basado en OpenAI genera y ejecuta un pipeline de Python. La tarea queda guardada como una automatización reutilizable, junto con su contrato de entrada, script y reglas de validación.

La plataforma también permite crear visualizaciones mediante lenguaje natural. El agente analiza un CSV o Excel, genera una especificación declarativa del gráfico y el frontend la renderiza. Las visualizaciones pueden guardarse en un canvas tipo dashboard y recalcularse automáticamente cuando se carga un nuevo archivo compatible.

## Objetivo

Crear una especie de combinación entre:

- Automatización de datos
- Chat con IA
- Generación de código Python
- Dashboard interactivo
- BI mediante lenguaje natural

La idea principal es que el usuario no tenga que programar ni diseñar manualmente los procesos o visualizaciones.

## Flujo principal

### Automatizaciones

```text
Archivo + instrucción del usuario
            ↓
       OpenAI Agent
            ↓
    Análisis de archivos
            ↓
   Generación de Python
            ↓
       Ejecución segura
            ↓
      Validación del resultado
            ↓
     Guardar automatización
```

Ejemplo:

> "Compara las ventas de estos dos archivos por región y genera un Excel con las diferencias."

El sistema:

1. Analiza los archivos.
2. Detecta las columnas disponibles.
3. Interpreta la tarea.
4. Genera un script Python.
5. Ejecuta el script.
6. Valida el resultado.
7. Entrega el archivo generado.
8. Guarda la automatización.

Posteriormente el usuario podrá ejecutar la misma tarea simplemente cargando nuevos archivos.

## Contrato de una automatización

Cada automatización debe almacenar:

```text
Automation
├── id
├── name
├── description
├── user_instruction
├── input_schema
├── python_script
├── requirements
├── output_schema
├── validation_rules
├── example_input
├── example_output
├── created_at
└── updated_at
```

El `input_schema` describe cómo deben ser los archivos futuros.

Ejemplo:

```json
{
  "files": [
    {
      "name": "ventas.xlsx",
      "type": "xlsx",
      "required_columns": [
        "fecha",
        "producto",
        "region",
        "cantidad",
        "valor"
      ]
    }
  ]
}
```

Cuando el usuario vuelva a utilizar la automatización, el sistema valida primero los archivos contra este contrato.

Si no cumplen:

```text
Archivo incompatible

Falta la columna:
valor

Columnas esperadas:
fecha
producto
region
cantidad
valor
```

## Visualizaciones

La segunda funcionalidad principal es crear visualizaciones mediante lenguaje natural.

Ejemplo:

> "Genera una gráfica de ventas mensuales por región."

El agente no debe generar HTML arbitrario.

Debe generar una especificación estructurada:

```json
{
  "type": "line",
  "title": "Ventas mensuales por región",
  "x": {
    "field": "fecha",
    "aggregation": "month"
  },
  "y": {
    "field": "valor",
    "aggregation": "sum"
  },
  "group_by": "region"
}
```

El frontend interpreta esta especificación y genera el gráfico.

La visualización se convierte así en un objeto persistente.

```text
Visual
├── id
├── dashboard_id
├── dataset_id
├── specification
├── position
├── size
├── created_at
└── updated_at
```

## Canvas

El usuario tendrá una pestaña tipo dashboard/canvas.

Podrá:

- Arrastrar visualizaciones.
- Cambiar tamaño.
- Reorganizar visualizaciones.
- Eliminar visualizaciones.
- Crear nuevas visualizaciones mediante chat.
- Guardar dashboards.
- Cargar nuevos archivos.
- Actualizar automáticamente los gráficos.

El canvas no debe almacenar los valores de las gráficas.

Debe almacenar la consulta o especificación necesaria para regenerarlas.

```text
Dataset
   ↓
Visual specification
   ↓
Query / transformation
   ↓
Chart
   ↓
Canvas
```

Cuando llega un nuevo Excel:

```text
Nuevo archivo
     ↓
Validación de schema
     ↓
Normalización
     ↓
Recalcular visualizaciones
     ↓
Actualizar dashboard
```

## Chat de visualizaciones

El usuario podrá interactuar con el dashboard mediante lenguaje natural.

Ejemplos:

> "Genera una gráfica de ventas por región."

> "Ahora hazla de barras."

> "Agrega los 10 productos con mayor crecimiento."

> "Pon esta gráfica arriba y hazla el doble de grande."

> "Guarda este dashboard."

El agente deberá interpretar cada solicitud y producir modificaciones estructuradas sobre el dashboard.

## Arquitectura

```text
                         FRONTEND
                            │
              ┌─────────────┴─────────────┐
              │                           │
          Automation                    Canvas
              │                           │
              │                         Chat
              └─────────────┬─────────────┘
                            │
                         FastAPI
                            │
                 ┌──────────┴──────────┐
                 │                     │
          Automation Agent       Visualization Agent
                 │                     │
                 ▼                     ▼
          Python Generator       Visual Spec
                 │                     │
                 ▼                     ▼
           Sandbox Runner          ECharts
                 │                     │
                 └──────────┬──────────┘
                            │
                       PostgreSQL
                            │
                       File Storage
                            │
                          OpenAI
```

## Stack inicial

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- ECharts
- React Grid Layout
- WebSocket o SSE para streaming

### Backend

- Python
- FastAPI
- Pydantic
- Pandas
- OpenPyXL
- PyPDF
- python-docx
- PostgreSQL
- SQLAlchemy

### IA

Inicialmente se utilizará la API de OpenAI.

El modelo se utilizará para:

- Interpretar instrucciones.
- Analizar schemas.
- Generar código Python.
- Generar especificaciones de visualización.
- Validar resultados.
- Corregir scripts cuando fallen.
- Interactuar con herramientas del backend.

La arquitectura debe mantener el proveedor de IA desacoplado para permitir posteriormente utilizar modelos locales.

```text
LLM Provider
     │
     ▼
AI Service Interface
     │
 ┌───┴───────────────┐
 │                   │
OpenAI            Local LLM
```

## Agente de automatización

El agente no debe tener acceso irrestricto al sistema operativo.

Debe trabajar mediante herramientas controladas.

Ejemplo conceptual:

```text
Agent
 │
 ├── inspect_file
 ├── inspect_dataframe
 ├── generate_python
 ├── execute_python
 ├── inspect_output
 └── validate_result
```

Flujo:

```text
User instruction
       ↓
Inspect files
       ↓
Understand task
       ↓
Generate Python
       ↓
Execute
       ↓
Error?
  ┌────┴────┐
 YES        NO
  ↓          ↓
Fix code   Validate
  ↓          ↓
Execute     Save
```

## Ejecución de Python

La ejecución del código generado debe realizarse de forma aislada.

Para el MVP se puede comenzar con un proceso separado y restricciones básicas.

La arquitectura debe permitir posteriormente utilizar:

- Docker sandbox
- Resource limits
- Timeout
- Filesystem aislado
- Network restrictions

Nunca se debe ejecutar código generado por el modelo directamente dentro del proceso principal de FastAPI.

## Archivos soportados

### MVP

- CSV
- XLSX

### Segunda fase

- PDF
- DOCX
- JSON
- TXT

### Futuro

- Imágenes
- PowerPoint
- múltiples fuentes de datos
- bases de datos

## Flujo de archivos

```text
Upload
  ↓
File validation
  ↓
File storage
  ↓
Metadata extraction
  ↓
Schema detection
  ↓
Agent
```

El sistema debe mantener separados:

```text
Original file
Processed data
Generated output
```

## Seguridad

La generación de código es una de las partes críticas del sistema.

El agente nunca debe poder:

- Ejecutar comandos arbitrarios del sistema.
- Acceder a credenciales.
- Leer archivos fuera del workspace.
- Modificar el servidor.
- Realizar conexiones de red arbitrarias.
- Acceder directamente a variables de entorno sensibles.

El workspace de cada ejecución debe estar aislado.

## Base de datos

Entidades principales:

```text
User
 │
 ├── Automation
 │       ├── AutomationRun
 │       └── Files
 │
 ├── Dataset
 │       └── Files
 │
 └── Dashboard
         └── Visual
```

### AutomationRun

Debe registrar:

```text
id
automation_id
input_files
generated_script
execution_time
status
stdout
stderr
output_files
created_at
```

Esto permitirá mostrar al usuario el historial de ejecuciones.

## UI

La aplicación tendrá inicialmente cuatro áreas principales:

```text
┌─────────────────────────────────────────────┐
│ AgentCanvas                                 │
├────────────┬────────────────────────────────┤
│            │                                │
│ Automate   │                                │
│            │                                │
│ Visualize  │        Main Workspace          │
│            │                                │
│ Canvas     │                                │
│            │                                │
│ History    │                                │
│            │                                │
└────────────┴────────────────────────────────┘
```

### Automate

Zona de upload + chat.

```text
Drop files here

┌────────────────────────────────────────┐
│ What do you want to do?                │
│                                        │
│ Compare both Excel files and generate  │
│ a report with the differences...       │
└────────────────────────────────────────┘
```

Después de crear la automatización:

```text
Automation created

Compare monthly sales

Required:
✓ XLSX
✓ Columns: date, product, region, value

[Run automation]
```

### Visualize

Zona de datos + chat.

```text
sales.xlsx

"What would you like to visualize?"
```

El resultado aparece directamente como visual.

### Canvas

Dashboard con drag & drop.

Cada visual debe ser un componente independiente.

## MVP del puente

El objetivo de los primeros tres días no es implementar toda la plataforma.

El MVP debe cubrir solamente:

```text
CSV/XLSX
   ↓
Upload
   ↓
Chat
   ↓
OpenAI
   ↓
Python generation
   ↓
Python execution
   ↓
Output file
```

y:

```text
CSV/XLSX
   ↓
Chat
   ↓
"Create a sales chart"
   ↓
OpenAI
   ↓
Visual specification
   ↓
ECharts
   ↓
Save
   ↓
Canvas
```

Finalmente:

```text
New Excel
   ↓
Same schema
   ↓
Recalculate saved visuals
   ↓
Updated dashboard
```

## Roadmap

### v0.1

- [ ] Crear repositorio.
- [ ] Crear frontend React.
- [ ] Crear backend FastAPI.
- [ ] Configurar OpenAI.
- [ ] Upload CSV.
- [ ] Upload XLSX.
- [ ] Inspección automática de schema.
- [ ] Chat de automatización.
- [ ] Generación de Python.
- [ ] Ejecución aislada.
- [ ] Descarga de resultados.

### v0.2

- [ ] Persistir automatizaciones.
- [ ] Persistir scripts.
- [ ] Persistir schemas.
- [ ] Validar nuevos archivos.
- [ ] Historial de ejecuciones.
- [ ] Mostrar errores de ejecución.
- [ ] Agregar ciclo automático de corrección.

### v0.3

- [ ] Visualizaciones con ECharts.
- [ ] Generación de visual specs.
- [ ] Bar chart.
- [ ] Line chart.
- [ ] Pie chart.
- [ ] Scatter plot.
- [ ] KPI cards.
- [ ] Tablas.

### v0.4

- [ ] Canvas.
- [ ] Drag & drop.
- [ ] Resize.
- [ ] Guardar dashboard.
- [ ] Persistir visualizaciones.
- [ ] Recalcular visualizaciones con nuevos archivos.

### v0.5

- [ ] PDF.
- [ ] DOCX.
- [ ] Mejor sandbox.
- [ ] Authentication.
- [ ] Multi-user.
- [ ] Storage externo.
- [ ] Versionado de automatizaciones.

## Principio fundamental

El sistema no debe guardar simplemente resultados.

Debe guardar **la lógica necesaria para reproducirlos**.

Una automatización no es:

```text
archivo → resultado
```

sino:

```text
input schema
      +
instruction
      +
python pipeline
      +
validation
      =
reusable automation
```

Una visualización tampoco debe ser:

```text
imagen
```

sino:

```text
dataset
   +
query
   +
visual specification
   +
layout
   =
reproducible visual
```

Esto permite que el sistema evolucione de un simple asistente de archivos a una plataforma de automatización y BI generativo.

## Resultado esperado

El usuario debería poder entrar, cargar un Excel y decir:

> "Quiero analizar las ventas y crear un dashboard con ventas mensuales, ventas por región, top 10 productos y crecimiento mensual."

El agente debe:

1. Analizar el archivo.
2. Crear las transformaciones necesarias.
3. Generar las visualizaciones.
4. Renderizarlas.
5. Colocarlas en el canvas.
6. Guardar el dashboard.

Después, el usuario carga el Excel del siguiente mes y obtiene automáticamente el mismo dashboard actualizado.

Ese es el concepto central de AgentCanvas AI.
