import { useState } from "react";
import { CodeIcon } from "./Icons";

/** El cálculo exacto, en Python.
 *
 * No es una ilustración ni una aproximación: es el mismo algoritmo que ejecuta
 * el motor, generado a partir de la especificación. Hay un test en el backend
 * que ejecuta este código y compara el resultado con el del motor, así que si
 * alguna vez dejaran de coincidir, el test se pone rojo.
 *
 * Está aquí porque una cifra que no se puede auditar no vale mucho. */
export function HowItWorks({ code }: { code: string | null }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!code) return null;

  return (
    <div className="border-t border-bone-200">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-xs text-ink-400 transition-colors hover:bg-bone-100 hover:text-ink-700"
      >
        <CodeIcon />
        Cómo se calcula
        <span className="ml-auto text-ink-300">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="relative bg-bone-100">
          <button
            type="button"
            onClick={async () => {
              await navigator.clipboard.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="absolute top-1.5 right-1.5 rounded border border-bone-300 bg-bone-50 px-1.5 py-0.5 text-[10px] text-ink-400 transition-colors hover:text-clay-600"
          >
            {copied ? "copiado" : "copiar"}
          </button>
          <pre className="overflow-x-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-700">
            {code}
          </pre>
        </div>
      )}
    </div>
  );
}
