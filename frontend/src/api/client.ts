import type {
  CanvasSummary,
  Conversation,
  DashboardDetail,
  Message,
  Placement,
  Turn,
  VisualSpec,
} from "./types";

/** Error del backend con su detalle intacto.
 *
 * El backend se toma la molestia de decir qué columna falta; perder eso al
 * cruzar la frontera y mostrar "Error 422" sería tirar el trabajo. */
export class ApiFailure extends Error {
  // Campos declarados y asignados a mano: `erasableSyntaxOnly` prohíbe las
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
    if (Array.isArray(body?.detail)) {
      const problems = body.detail.map((issue: { msg?: string }) => issue.msg ?? "inválido");
      return new ApiFailure(response.status, "ValidationError", "Petición inválida", problems);
    }
  } catch {
    /* respuesta sin JSON */
  }
  return new ApiFailure(response.status, "Error", `El servidor respondió ${response.status}`);
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  /* --- conversación --- */

  listConversations: () => request<Conversation[]>("/api/conversations"),

  startConversation: () => request<Conversation>("/api/conversations", { method: "POST" }),

  messages: (id: string) => request<Message[]>(`/api/conversations/${id}/messages`),

  deleteConversation: (id: string) =>
    request<void>(`/api/conversations/${id}`, { method: "DELETE" }),

  /** El texto y el adjunto viajan juntos: así funciona un chat. */
  send(conversationId: string, text: string, file: File | null) {
    const form = new FormData();
    form.append("text", text);
    if (file) form.append("file", file);
    return request<Turn>(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: form,
    });
  },

  /* --- lienzos --- */

  listCanvases: () => request<CanvasSummary[]>("/api/dashboards"),

  createCanvas: (name: string) => request<{ id: string }>("/api/dashboards", json({ name })),

  openCanvas: (id: string) => request<DashboardDetail>(`/api/dashboards/${id}`),

  renameCanvas: (id: string, name: string) =>
    request<unknown>(`/api/dashboards/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  deleteCanvas: (id: string) => request<void>(`/api/dashboards/${id}`, { method: "DELETE" }),

  pin: (canvasId: string, datasetId: string, spec: VisualSpec) =>
    request<{ id: string }>(
      `/api/dashboards/${canvasId}/visuals`,
      json({ dataset_id: datasetId, spec }),
    ),

  saveLayout: (canvasId: string, items: { visual_id: string; placement: Placement }[]) =>
    request<unknown>(`/api/dashboards/${canvasId}/layout`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    }),

  removeVisual: (canvasId: string, visualId: string) =>
    request<void>(`/api/dashboards/${canvasId}/visuals/${visualId}`, { method: "DELETE" }),
};
