import { useState } from "react";
import type { Artifact, CanvasSummary, Cell, Message } from "../api/types";
import { formatCell, formatNumber } from "../charts/options";
import { HowItWorks } from "./HowItWorks";
import { PaperclipIcon, PinIcon, TableIcon } from "./Icons";
import { Markdown } from "./Markdown";
import { Python } from "./Python";
import { Visual } from "./Visual";

/** Un mensaje de la conversación, con lo que el asistente haya producido.
 *
 * Los gráficos viven aquí dentro, no en otra pantalla: es sobre ellos sobre lo
 * que se itera, y sacarlos de la conversación rompería el hilo. */
export function Bubble({
  message,
  canvases,
  onPin,
}: {
  message: Message;
  canvases: CanvasSummary[];
  onPin: (artifact: Artifact, canvasId: string | null, name: string) => Promise<void>;
}) {
  const mine = message.role === "user";

  return (
    <div className={`flex flex-col gap-2 ${mine ? "items-end" : "items-start"}`}>
      {(message.text || message.attachments.length > 0) && (
        <div
          className={`max-w-[46rem] rounded-card px-3.5 py-2.5 ${
            mine
              ? "bg-clay-500 text-bone-50"
              : "border border-bone-300 bg-bone-50 text-ink-900"
          }`}
        >
          {/* El asistente escribe en markdown; sin renderizar se ven los
              asteriscos, que es peor que si no los hubiera puesto. */}
          {mine ? (
            <p className="text-sm whitespace-pre-wrap">{message.text}</p>
          ) : (
            <Markdown text={message.text} />
          )}
          {message.attachments.map((attachment) => (
            <span
              key={attachment.file_id}
              className={`mt-1.5 flex items-center gap-1.5 text-xs ${
                mine ? "text-bone-100/80" : "text-ink-400"
              }`}
            >
              <PaperclipIcon />
              {attachment.filename}
            </span>
          ))}
        </div>
      )}

      {message.artifacts.map((artifact, index) => (
        <ArtifactCard
          key={index}
          artifact={artifact}
          canvases={canvases}
          onPin={onPin}
        />
      ))}
    </div>
  );
}

function ArtifactCard({
  artifact,
  canvases,
  onPin,
}: {
  artifact: Artifact;
  canvases: CanvasSummary[];
  onPin: (artifact: Artifact, canvasId: string | null, name: string) => Promise<void>;
}) {
  if (artifact.kind === "dataset") {
    return <DatasetCard artifact={artifact} />;
  }
  if (artifact.kind === "query") {
    return <QueryCard artifact={artifact} />;
  }
  if (artifact.kind !== "visual" || !artifact.spec) {
    return null;
  }
  return <VisualCard artifact={artifact} canvases={canvases} onPin={onPin} />;
}

/** La consulta que hay detrás de una cifra escrita en el texto.
 *
 * Cuando el asistente responde "la media es 5,55" no queda ninguna tarjeta, y
 * antes tampoco quedaba rastro de si había calculado ese número o lo recordaba.
 * Con un conjunto conocido las dos cosas dan lo mismo; con los datos de alguien,
 * una de las dos miente.
 *
 * Va plegada y en gris: es una nota al pie, no el contenido. Quien se fíe sigue
 * leyendo; quien no, la abre y ve las filas y el Python que las produce. */
function QueryCard({ artifact }: { artifact: Artifact }) {
  const [open, setOpen] = useState(false);
  const rows = artifact.data?.rows ?? [];
  const columns = artifact.data?.columns ?? [];

  return (
    <div className="w-full max-w-[46rem] overflow-hidden rounded-card border border-dashed border-bone-300">
      <button
        type="button"
        onClick={() => setOpen((shown) => !shown)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-xs text-ink-400 transition-colors hover:bg-bone-100 hover:text-ink-700"
      >
        <TableIcon />
        <span className="truncate">
          Consultado: {artifact.spec?.title ?? "los datos"}
        </span>
        <span className="ml-auto shrink-0 text-ink-300 tabular">
          {artifact.error ? "sin datos" : `${rows.length} fila(s)`}
        </span>
      </button>

      {open && (
        <div className="border-t border-bone-200 bg-bone-50 px-3 py-2">
          {artifact.error ? (
            <p className="text-xs text-alert">{artifact.error}</p>
          ) : (
            <div className="overflow-x-auto rounded border border-bone-200">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-bone-100">
                    {columns.map((column) => (
                      <th
                        key={column.key}
                        className="border-b border-bone-200 px-2 py-1 text-left text-[10px] font-medium whitespace-nowrap text-ink-500"
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      {columns.map((column) => (
                        <td
                          key={column.key}
                          className="border-b border-bone-100 px-2 py-1 whitespace-nowrap text-ink-700 last:border-0"
                        >
                          {formatNumber(row[column.key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {artifact.code && (
            <pre className="mt-2 overflow-x-auto rounded border border-bone-200 bg-bone-100 px-2.5 py-2">
              <Python code={artifact.code} />
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function DatasetCard({ artifact }: { artifact: Artifact }) {
  // Tolerante a que falten: una respuesta de un backend mas antiguo, o una
  // conversacion cacheada, no puede dejar la pantalla en blanco.
  const warnings = artifact.warnings ?? [];
  const preview = artifact.preview ?? [];

  return (
    <div className="w-full max-w-[46rem] rounded-card border border-bone-300 bg-bone-50 px-3.5 py-3">
      <div className="flex items-center gap-2">
        <span className="text-clay-500">
          <TableIcon />
        </span>
        <span className="text-sm font-medium text-ink-900">{artifact.name}</span>
        <span className="text-xs text-ink-400 tabular">{artifact.row_count} filas</span>
      </div>
      {/* De dónde salió: en un Excel caótico, saber que se leyó la hoja
          correcta importa tanto como el resultado. */}
      {artifact.origin && <p className="mt-1 text-xs text-ink-400">{artifact.origin}</p>}

      {/* Lo que olió raro. Antes solo lo veía el modelo, y una extracción
          sospechosa pasaba inadvertida hasta que un gráfico salía mal. */}
      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1 rounded border border-notice/30 bg-notice/5 px-2.5 py-1.5">
          {warnings.map((warning) => (
            <li key={warning} className="text-xs text-ink-700">
              {warning}
            </li>
          ))}
        </ul>
      )}

      {/* Las primeras filas: es lo que permite decir "esa no es la tabla que
          quería" antes de construir nada encima. */}
      {preview.length > 0 && <Peek rows={preview} />}

      {preview.length === 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {(artifact.columns ?? []).map((column) => (
            <span
              key={column}
              className="rounded border border-bone-300 px-1.5 py-0.5 font-mono text-[10px] text-ink-500"
            >
              {column}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Peek({ rows }: { rows: Record<string, Cell>[] }) {
  const columns = Object.keys(rows[0] ?? {});
  return (
    <div className="mt-2 overflow-x-auto rounded border border-bone-200">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="bg-bone-100">
            {columns.map((column) => (
              <th
                key={column}
                className="border-b border-bone-200 px-2 py-1 text-left font-mono text-[10px] font-medium whitespace-nowrap text-ink-500"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td
                  key={column}
                  className="border-b border-bone-100 px-2 py-1 whitespace-nowrap text-ink-700 last:border-0"
                >
                  {formatCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VisualCard({
  artifact,
  canvases,
  onPin,
}: {
  artifact: Artifact;
  canvases: CanvasSummary[];
  onPin: (artifact: Artifact, canvasId: string | null, name: string) => Promise<void>;
}) {
  const [picking, setPicking] = useState(false);
  const [saved, setSaved] = useState(false);
  const [newName, setNewName] = useState("");

  async function pin(canvasId: string | null, name = "") {
    await onPin(artifact, canvasId, name);
    setPicking(false);
    setSaved(true);
  }

  return (
    <div className="relative w-full max-w-[46rem] overflow-hidden rounded-card border border-bone-300 bg-bone-50">
      <header className="flex items-center justify-between gap-2 border-b border-bone-200 px-3 py-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium text-ink-900">{artifact.spec?.title}</h3>
          <p className="text-xs text-ink-400">{artifact.spec?.type}</p>
        </div>
        {saved ? (
          <span className="text-xs text-ok">Guardado</span>
        ) : (
          <button
            type="button"
            onClick={() => setPicking((open) => !open)}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-ink-400 transition-colors hover:bg-bone-200 hover:text-clay-600"
          >
            <PinIcon />
            Guardar en lienzo
          </button>
        )}
      </header>

      {picking && (
        <div className="border-b border-bone-200 bg-bone-100 px-3 py-2">
          <div className="flex flex-wrap gap-1.5">
            {canvases.map((canvas) => (
              <button
                key={canvas.id}
                type="button"
                onClick={() => void pin(canvas.id)}
                className="rounded-full border border-bone-300 bg-bone-50 px-2.5 py-1 text-xs text-ink-700 transition-colors hover:border-clay-500 hover:text-clay-600"
              >
                {canvas.name}
                <span className="ml-1 text-ink-300 tabular">{canvas.visual_count}</span>
              </button>
            ))}
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void pin(null, newName.trim() || "Nuevo lienzo");
            }}
            className="mt-2 flex gap-1.5"
          >
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="…o crea un lienzo nuevo"
              className="flex-1 rounded border border-bone-300 bg-bone-50 px-2 py-1 text-xs text-ink-900 outline-none placeholder:text-ink-300 focus:border-clay-500"
            />
            <button
              type="submit"
              className="rounded bg-clay-500 px-2.5 py-1 text-xs text-bone-50 hover:bg-clay-600"
            >
              Crear
            </button>
          </form>
        </div>
      )}

      <div className="h-72 p-2">
        {artifact.data ? (
          <Visual spec={artifact.spec!} data={artifact.data} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <p className="text-xs font-medium text-alert">No se pudo calcular</p>
            <p className="text-xs text-ink-400">{artifact.error}</p>
          </div>
        )}
      </div>

      {/* El cálculo exacto, para quien quiera comprobarlo. */}
      <HowItWorks code={artifact.code} />
    </div>
  );
}
