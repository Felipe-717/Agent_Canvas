/* Espejo de los contratos del backend.
 *
 * `VisualSpec` y `VisualData` se copian tal cual a proposito: son el contrato
 * publico entre el motor determinista y esta pantalla. Si divergen, el sintoma
 * es un grafico vacio, asi que conviene que rompan en tiempo de compilacion.
 */

export type ChartType = "line" | "bar" | "area" | "pie" | "scatter" | "kpi" | "table";

export type Aggregation =
  | "sum"
  | "avg"
  | "min"
  | "max"
  | "count"
  | "count_distinct"
  | "median"
  | "none";

export type TimeGrain = "day" | "week" | "month" | "quarter" | "year";

export type ColumnType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "date"
  | "datetime"
  | "unknown";

export interface Dimension {
  field: string;
  time_grain: TimeGrain | null;
  label: string | null;
}

export interface Measure {
  field: string | null;
  aggregation: Aggregation;
  label: string | null;
}

export interface Sort {
  by: string;
  direction: "asc" | "desc";
}

export interface VisualSpec {
  type: ChartType;
  title: string;
  x: Dimension | null;
  y: Measure[];
  group_by: Dimension | null;
  filters: unknown[];
  sort: Sort | null;
  limit: number | null;
}

export interface ResultColumn {
  key: string;
  label: string;
  type: ColumnType;
}

export type Cell = string | number | boolean | null;

export interface VisualData {
  columns: ResultColumn[];
  rows: Record<string, Cell>[];
  truncated: boolean;
}

export interface Column {
  name: string;
  original_name: string;
  type: ColumnType;
  nullable: boolean;
}

export interface Dataset {
  id: string;
  name: string;
  row_count: number;
  fingerprint: string;
  columns: Column[];
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestResult {
  dataset: Dataset;
  version: { id: string; row_count: number; created_at: string };
  created_dataset: boolean;
  preview: Record<string, Cell>[];
}

export interface Trace {
  attempts: number;
  repairs: number;
  usage: { input_tokens: number; output_tokens: number; cached_input_tokens: number };
  problems: string[];
}

export interface VisualResult {
  spec: VisualSpec;
  data: VisualData;
  trace: Trace | null;
}

export interface Placement {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface DashboardSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardVisual {
  id: string;
  dataset_id: string;
  spec: VisualSpec;
  placement: Placement;
  data: VisualData | null;
  /** Por que no se pudo calcular. Excluyente con `data`. */
  error: string | null;
}

export interface DashboardDetail {
  dashboard: DashboardSummary;
  visuals: DashboardVisual[];
  grid_columns: number;
}

export interface ApiError {
  error: string;
  detail: string;
  problems: string[];
}

/* --- Conversación --------------------------------------------------------- */

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface AttachmentRef {
  file_id: string;
  filename: string;
}

/** Lo que el asistente produjo dentro de un mensaje.
 *
 * De un gráfico llega su `spec` (que es lo guardado) y sus `data` (que se
 * acaban de calcular en el servidor). Si el origen ya no existe, llega `error`
 * en lugar de datos. */
export interface Artifact {
  kind: "dataset" | "visual" | "unknown";
  dataset_id: string;
  name: string | null;
  row_count: number | null;
  columns: string[] | null;
  origin: string | null;
  spec: VisualSpec | null;
  data: VisualData | null;
  error: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  attachments: AttachmentRef[];
  artifacts: Artifact[];
  created_at: string;
}

export interface Turn {
  user_message: Message;
  assistant_message: Message;
  trace: Trace;
}

/* --- Lienzos -------------------------------------------------------------- */

export interface CanvasSummary {
  id: string;
  name: string;
  visual_count: number;
  /** Un lienzo puede mezclar orígenes: cada visual guarda el suyo. */
  sources: { id: string; name: string }[];
  updated_at: string;
}
