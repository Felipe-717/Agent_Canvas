import type {
  DashboardDetail,
  DashboardSummary,
  Dataset,
  IngestResult,
  Placement,
  VisualResult,
  VisualSpec,
} from "./types";

/** Error del backend con su detalle intacto.
 *
 * El backend se toma la molestia de decir que columna falta; perder eso al
 * cruzar la frontera y mostrar "Error 422" seria tirar el trabajo. */
export class ApiFailure extends Error {
  // Campos declarados y asignados a mano: `erasableSyntaxOnly` prohibe las
  // propiedades de constructor, que no son borrables por el transpilador.
  readonly status: number;
  readonly kind: string;
  readonly problems: string[];

  constructor(status: number, kind: string, detail: string, problems: string[] = []) {
    super(detail);
    this.name = "ApiFailure";
    this.status = status;
    this.kind = kind;
    this.problems = problems;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw await toFailure(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function toFailure(response: Response): Promise<ApiFailure> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return new ApiFailure(response.status, body.error ?? "Error", body.detail, body.problems ?? []);
    }
    // Los errores de validacion de FastAPI traen otra forma.
    if (Array.isArray(body?.detail)) {
      const problems = body.detail.map((issue: { msg?: string }) => issue.msg ?? "invalido");
      return new ApiFailure(response.status, "ValidationError", "Peticion invalida", problems);
    }
  } catch {
    /* respuesta sin JSON */
  }
  return new ApiFailure(response.status, "Error", `El servidor respondio ${response.status}`);
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  listDatasets: () => request<Dataset[]>("/api/datasets"),

  getDataset: (id: string) => request<Dataset>(`/api/datasets/${id}`),

  upload(file: File, options: { datasetId?: string; name?: string } = {}) {
    const form = new FormData();
    form.append("file", file);
    if (options.datasetId) form.append("dataset_id", options.datasetId);
    if (options.name) form.append("name", options.name);
    return request<IngestResult>("/api/datasets", { method: "POST", body: form });
  },

  createVisual: (datasetId: string, instruction: string) =>
    request<VisualResult>(`/api/datasets/${datasetId}/visuals`, json({ instruction })),

  render: (datasetId: string, spec: VisualSpec) =>
    request<VisualResult>(`/api/datasets/${datasetId}/render`, json({ spec })),

  listDashboards: () => request<DashboardSummary[]>("/api/dashboards"),

  createDashboard: (name: string) =>
    request<DashboardSummary>("/api/dashboards", json({ name })),

  openDashboard: (id: string) => request<DashboardDetail>(`/api/dashboards/${id}`),

  renameDashboard: (id: string, name: string) =>
    request<DashboardSummary>(`/api/dashboards/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  addVisual: (dashboardId: string, datasetId: string, spec: VisualSpec) =>
    request<{ id: string }>(
      `/api/dashboards/${dashboardId}/visuals`,
      json({ dataset_id: datasetId, spec }),
    ),

  saveLayout: (dashboardId: string, items: { visual_id: string; placement: Placement }[]) =>
    request<unknown>(`/api/dashboards/${dashboardId}/layout`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    }),

  removeVisual: (dashboardId: string, visualId: string) =>
    request<void>(`/api/dashboards/${dashboardId}/visuals/${visualId}`, { method: "DELETE" }),
};
