import { useState } from "react";
import { CodeIcon } from "./Icons";
import { Python } from "./Python";

/** El cálculo exacto, en Python.
 *
 * No es una ilustración ni una aproximación: es el mismo algoritmo que ejecuta
 * el motor, generado a partir de la especificación. Hay tests en el backend que
 * ejecutan este código y comparan el resultado con el del motor, así que si
 * alguna vez dejaran de coincidir, se ponen rojos.
 *
 * Está aquí porque una cifra que no se puede auditar no vale mucho.
 *
 * Se muestra tapando el cuerpo de la tarjeta en vez de empujarlo hacia abajo:
 * en el lienzo la altura la fija la rejilla, así que desplegar hacia abajo
 * dejaba el código pisando el gráfico. La tarjeta se da la vuelta y ya. */
export function HowItWorks({ code }: { code: string | null }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!code) return null;

  return (
    <>
      {open && (
        <div className="absolute inset-0 z-20 flex flex-col bg-bone-50">
          <header className="flex items-center justify-between border-b border-bone-200 px-3 py-2">
            <span className="flex items-center gap-1.5 text-xs font-medium text-ink-700">
              <CodeIcon />
              Cómo se calcula
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={async () => {
                  await navigator.clipboard.writeText(code);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                className="rounded border border-bone-300 px-1.5 py-0.5 text-[10px] text-ink-400 transition-colors hover:text-clay-600"
              >
                {copied ? "copiado" : "copiar"}
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Cerrar"
                className="rounded px-1.5 py-0.5 text-sm leading-none text-ink-300 transition-colors hover:bg-bone-200 hover:text-ink-700"
              >
                ×
              </button>
            </div>
          </header>
          <pre className="min-h-0 flex-1 overflow-auto px-3 py-2">
            <Python code={code} />
          </pre>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen(true)}
        // Fondo sólido: sin él, el gráfico se transparenta detrás de la barra.
        className="flex w-full shrink-0 items-center gap-1.5 border-t border-bone-200 bg-bone-50 px-3 py-1.5 text-left text-xs text-ink-400 transition-colors hover:bg-bone-100 hover:text-ink-700"
      >
        <CodeIcon />
        Cómo se calcula
      </button>
    </>
  );
}
