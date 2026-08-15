import type { CanvasSummary, Conversation } from "../api/types";
import { ChatIcon, GridIcon, PlusIcon, TrashIcon } from "./Icons";

/** Conversaciones arriba, lienzos abajo.
 *
 * Los conjuntos de datos ya no salen: son un detalle interno del que se habla
 * dentro de la conversación, no algo que el usuario tenga que administrar. */
export function Sidebar({
  conversations,
  activeConversation,
  canvases,
  activeCanvas,
  onOpenConversation,
  onNewConversation,
  onDeleteConversation,
  onOpenCanvas,
}: {
  conversations: Conversation[];
  activeConversation: string | null;
  canvases: CanvasSummary[];
  activeCanvas: string | null;
  onOpenConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
  onOpenCanvas: (id: string) => void;
}) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-bone-300 bg-bone-100">
      <div className="p-3">
        <button
          type="button"
          onClick={onNewConversation}
          className="flex w-full items-center justify-center gap-1.5 rounded-card bg-clay-500 px-3 py-2 text-sm font-medium text-bone-50 transition-colors hover:bg-clay-600"
        >
          <PlusIcon />
          Nueva conversación
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3">
        <Heading icon={<ChatIcon />} label="Conversaciones" />
        {conversations.length === 0 && <Hint>Todavía no has hablado con nadie.</Hint>}
        {conversations.map((conversation) => (
          <div key={conversation.id} className="group relative">
            <button
              type="button"
              onClick={() => onOpenConversation(conversation.id)}
              className={`mb-1 w-full truncate rounded px-2 py-1.5 pr-7 text-left text-sm transition-colors ${
                conversation.id === activeConversation
                  ? "bg-bone-200 text-ink-900"
                  : "text-ink-500 hover:bg-bone-200/60 hover:text-ink-900"
              }`}
            >
              {conversation.title}
            </button>
            <button
              type="button"
              onClick={() => onDeleteConversation(conversation.id)}
              aria-label="Borrar conversación"
              className="absolute top-1.5 right-1 rounded p-1 text-ink-300 opacity-0 transition-opacity group-hover:opacity-100 hover:text-alert"
            >
              <TrashIcon />
            </button>
          </div>
        ))}

        <Heading icon={<GridIcon />} label="Lienzos" />
        {canvases.length === 0 && (
          <Hint>Guarda un gráfico del chat y aparecerá aquí.</Hint>
        )}
        {canvases.map((canvas) => (
          <button
            key={canvas.id}
            type="button"
            onClick={() => onOpenCanvas(canvas.id)}
            className={`mb-1 w-full rounded px-2 py-1.5 text-left transition-colors ${
              canvas.id === activeCanvas
                ? "bg-bone-200 text-ink-900"
                : "text-ink-500 hover:bg-bone-200/60 hover:text-ink-900"
            }`}
          >
            <span className="flex items-baseline justify-between gap-2">
              <span className="truncate text-sm">{canvas.name}</span>
              <span className="shrink-0 text-xs text-ink-300 tabular">
                {canvas.visual_count}
              </span>
            </span>
            {/* Las fuentes, porque un lienzo puede mezclar varias. */}
            {canvas.sources.length > 0 && (
              <span className="mt-0.5 block truncate text-xs text-ink-300">
                {canvas.sources.map((source) => source.name).join(" · ")}
              </span>
            )}
          </button>
        ))}
      </div>
    </aside>
  );
}

function Heading({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <p className="mt-3 mb-1.5 flex items-center gap-1.5 text-xs font-medium tracking-wide text-ink-400 uppercase">
      {icon}
      {label}
    </p>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="px-2 pb-2 text-xs text-ink-300">{children}</p>;
}
