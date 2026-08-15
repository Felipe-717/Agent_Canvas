import { useState } from "react";
import { api, ApiFailure } from "../api/client";
import type { Dataset, VisualResult } from "../api/types";
import { Card } from "./Card";
import { ChartIcon, PinIcon } from "./Icons";
import { Visual } from "./Visual";

const SUGGESTIONS = [
  "Evolución mensual de las ventas",
  "Top 5 por importe",
  "Reparto por categoría",
  "Total acumulado",
];

/** Pestana de exploracion: pedir un grafico y verlo.
 *
 * Los resultados se acumulan hacia abajo en vez de sustituirse. Comparar dos
 * preguntas seguidas es el uso normal, y perder la anterior al hacer la
 * siguiente obligaria a repetirla. */
export function Explore({
  dataset,
  onPin,
}: {
  dataset: Dataset | null;
  onPin: (result: VisualResult) => Promise<void>;
}) {
  const [instruction, setInstruction] = useState("");
  const [results, setResults] = useState<VisualResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiFailure | null>(null);
  const [pinned, setPinned] = useState<Set<number>>(new Set());

  async function ask(text: string) {
    if (!dataset || !text.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      const result = await api.createVisual(dataset.id, text.trim());
      setResults((current) => [result, ...current]);
      setInstruction("");
    } catch (error) {
      setProblem(error as ApiFailure);
    } finally {
      setBusy(false);
    }
  }

  if (!dataset) {
    return (
      <Blank
        title="Empieza por un archivo"
        detail="Arrastra un CSV o un Excel en el panel de la izquierda."
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-bone-300 bg-bone-50 px-6 py-4">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void ask(instruction);
          }}
          className="flex gap-2"
        >
          <input
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder={`¿Qué quieres ver de ${dataset.name}?`}
            disabled={busy}
            className="flex-1 rounded-card border border-bone-300 bg-bone-50 px-3 py-2 text-sm text-ink-900 outline-none placeholder:text-ink-300 focus:border-clay-500 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !instruction.trim()}
            className="rounded-card bg-clay-500 px-4 py-2 text-sm font-medium text-bone-50 transition-colors hover:bg-clay-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Pensando…" : "Crear"}
          </button>
        </form>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={busy}
              onClick={() => void ask(suggestion)}
              className="rounded-full border border-bone-300 px-2.5 py-1 text-xs text-ink-500 transition-colors hover:border-clay-300 hover:text-clay-600 disabled:opacity-40"
            >
              {suggestion}
            </button>
          ))}
        </div>

        {problem && (
          <div className="mt-3 rounded border border-alert/30 bg-alert/5 px-3 py-2">
            <p className="text-sm text-alert">{problem.message}</p>
            {problem.problems.map((detail) => (
              <p key={detail} className="mt-0.5 text-xs text-ink-500">
                {detail}
              </p>
            ))}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        {results.length === 0 && !busy && (
          <Blank
            title="Pregunta en tus palabras"
            detail="Describe lo que quieres ver. El gráfico se elige solo."
          />
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          {results.map((result, index) => (
            <div key={index} className="h-80">
              <Card
                title={result.spec.title}
                subtitle={describe(result)}
                actions={
                  <button
                    type="button"
                    disabled={pinned.has(index)}
                    onClick={async () => {
                      await onPin(result);
                      setPinned((current) => new Set(current).add(index));
                    }}
                    className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-ink-400 transition-colors hover:bg-bone-200 hover:text-clay-600 disabled:text-ok disabled:hover:bg-transparent"
                  >
                    <PinIcon />
                    {pinned.has(index) ? "En el panel" : "Fijar"}
                  </button>
                }
              >
                <Visual spec={result.spec} data={result.data} />
              </Card>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Lo que costo y si el agente tuvo que corregirse.
 *
 * Se ensena porque un agente que se corrige en silencio es un agente que nadie
 * puede mejorar. */
function describe(result: VisualResult): string {
  const parts: string[] = [result.spec.type];
  if (result.data.truncated) parts.push("recortado");
  if (result.trace && result.trace.repairs > 0) {
    parts.push(`${result.trace.repairs} corrección${result.trace.repairs > 1 ? "es" : ""}`);
  }
  return parts.join(" · ");
}

function Blank({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
      <span className="text-ink-300">
        <ChartIcon />
      </span>
      <p className="text-sm font-medium text-ink-500">{title}</p>
      <p className="max-w-xs text-xs text-ink-400">{detail}</p>
    </div>
  );
}
