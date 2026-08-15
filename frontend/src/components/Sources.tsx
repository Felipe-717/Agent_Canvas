import { useRef, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { Source } from "../api/types";
import { RefreshIcon } from "./Icons";

/** Las fuentes del lienzo, cada una con su botón de actualizar.
 *
 * Un lienzo puede mezclar varios orígenes, así que no hay un único "actualizar
 * archivo": se actualiza el que ha cambiado. El archivo nuevo se relee con las
 * mismas coordenadas que la primera vez, sin volver a preguntarle nada al
 * modelo. */
export function Sources({
  sources,
  onRefreshed,
}: {
  sources: Source[];
  onRefreshed: () => void;
}) {
  if (sources.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {sources.map((source) => (
        <SourceChip key={source.id} source={source} onRefreshed={onRefreshed} />
      ))}
    </div>
  );
}

function SourceChip({ source, onRefreshed }: { source: Source; onRefreshed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function refresh(file: File) {
    setBusy(true);
    setFailure(null);
    setResult(null);
    try {
      const updated = await api.refreshSource(source.id, file);
      const delta = updated.row_count - updated.previous_rows;
      setResult(
        `${updated.row_count} filas${delta ? ` (${delta > 0 ? "+" : ""}${delta})` : ""}`,
      );
      onRefreshed();
      setTimeout(() => setResult(null), 4000);
    } catch (error) {
      setFailure(error as ApiFailure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-1.5 rounded-full border border-bone-300 bg-bone-50 py-1 pr-1 pl-2.5">
        <span className="text-xs text-ink-700">{source.name}</span>
        <span className="text-xs text-ink-300 tabular">{source.row_count}</span>
        <button
          type="button"
          disabled={busy || !source.can_refresh}
          onClick={() => input.current?.click()}
          title={
            source.can_refresh
              ? `Actualizar ${source.name} con un archivo nuevo`
              : "No se guardó cómo se extrajo: vuelve a prepararlo desde el chat"
          }
          aria-label={`Actualizar ${source.name}`}
          className="rounded-full p-1 text-ink-400 transition-colors hover:bg-bone-200 hover:text-clay-600 disabled:opacity-30"
        >
          <RefreshIcon />
        </button>
      </div>

      <input
        ref={input}
        type="file"
        accept=".csv,.xlsx,.xls,.txt,.tsv"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void refresh(file);
          event.target.value = "";
        }}
      />

      {busy && <Note>actualizando…</Note>}
      {result && <Note tone="ok">{result}</Note>}
      {failure && (
        <Note tone="alert" onDismiss={() => setFailure(null)}>
          {failure.problems[0] ?? failure.message}
        </Note>
      )}
    </div>
  );
}

function Note({
  children,
  tone = "muted",
  onDismiss,
}: {
  children: React.ReactNode;
  tone?: "muted" | "ok" | "alert";
  onDismiss?: () => void;
}) {
  const colors = {
    muted: "border-bone-300 text-ink-400",
    ok: "border-ok/40 text-ok",
    alert: "border-alert/40 text-alert",
  }[tone];
  return (
    <div
      className={`absolute top-full right-0 z-20 mt-1 max-w-64 rounded border bg-bone-50 px-2 py-1 text-xs shadow-paper ${colors}`}
    >
      {children}
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="ml-1.5 text-ink-300">
          ×
        </button>
      )}
    </div>
  );
}
