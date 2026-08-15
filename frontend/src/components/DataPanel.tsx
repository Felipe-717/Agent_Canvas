import { useRef, useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { Dataset } from "../api/types";
import { UploadIcon } from "./Icons";

/** Columna izquierda: los conjuntos de datos y su esquema.
 *
 * Muestra el esquema porque es el contrato: es lo que el usuario tiene que
 * respetar en el archivo del mes siguiente para que sus graficos sigan
 * funcionando. Esconderlo lo convertiria en una sorpresa. */
export function DataPanel({
  datasets,
  selected,
  onSelect,
  onChanged,
}: {
  datasets: Dataset[];
  selected: Dataset | null;
  onSelect: (dataset: Dataset) => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiFailure | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File, datasetId?: string) {
    setBusy(true);
    setProblem(null);
    try {
      const result = await api.upload(file, { datasetId });
      onChanged();
      onSelect(result.dataset);
    } catch (error) {
      setProblem(error as ApiFailure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-bone-300 bg-bone-100">
      <div className="p-3">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files[0];
            if (file) void upload(file);
          }}
          onClick={() => input.current?.click()}
          className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-card border border-dashed px-3 py-5 text-center transition-colors ${
            dragging
              ? "border-clay-500 bg-clay-50"
              : "border-bone-400 bg-bone-50 hover:border-ink-300"
          }`}
        >
          <span className="text-ink-400">
            <UploadIcon />
          </span>
          <span className="text-xs text-ink-500">
            {busy ? "Procesando…" : "Arrastra un CSV o Excel"}
          </span>
        </div>
        <input
          ref={input}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
        {problem && <Problem failure={problem} />}
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 pb-3">
        {datasets.map((dataset) => {
          const active = dataset.id === selected?.id;
          return (
            <button
              key={dataset.id}
              type="button"
              onClick={() => onSelect(dataset)}
              className={`mb-1.5 w-full rounded-card border px-2.5 py-2 text-left transition-colors ${
                active
                  ? "border-clay-500 bg-bone-50"
                  : "border-transparent bg-bone-50/60 hover:border-bone-300"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-sm font-medium text-ink-900">{dataset.name}</span>
                <span className="shrink-0 text-xs text-ink-300 tabular">
                  {dataset.row_count} filas
                </span>
              </div>
              <span className="text-xs text-ink-400">{dataset.columns.length} columnas</span>
            </button>
          );
        })}
      </div>

      {selected && (
        <div className="border-t border-bone-300 bg-bone-50 p-3">
          <p className="mb-2 text-xs font-medium tracking-wide text-ink-400 uppercase">
            Esquema
          </p>
          <ul className="max-h-48 space-y-1 overflow-auto">
            {selected.columns.map((column) => (
              <li key={column.name} className="flex items-baseline justify-between gap-2 text-xs">
                <span className="truncate text-ink-700" title={column.original_name}>
                  {column.name}
                </span>
                <span className="shrink-0 font-mono text-[10px] text-ink-300">{column.type}</span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              const picker = document.createElement("input");
              picker.type = "file";
              picker.accept = ".csv,.xlsx";
              picker.onchange = () => {
                const file = picker.files?.[0];
                if (file) void upload(file, selected.id);
              };
              picker.click();
            }}
            className="mt-3 w-full rounded border border-bone-300 px-2 py-1.5 text-xs text-ink-500 transition-colors hover:border-clay-500 hover:text-clay-600"
          >
            Actualizar con un archivo nuevo
          </button>
        </div>
      )}
    </aside>
  );
}

function Problem({ failure }: { failure: ApiFailure }) {
  return (
    <div className="mt-2 rounded border border-alert/30 bg-alert/5 px-2.5 py-2">
      <p className="text-xs font-medium text-alert">{failure.message}</p>
      {failure.problems.length > 0 && (
        <ul className="mt-1 space-y-0.5">
          {failure.problems.map((problem) => (
            <li key={problem} className="text-xs text-ink-500">
              {problem}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
