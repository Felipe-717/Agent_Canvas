import { useRef, useState } from "react";
import { PaperclipIcon, SendIcon } from "./Icons";

/** La caja de escribir, con el botón de adjuntar.
 *
 * El adjunto se queda en espera hasta que se envía, junto al texto: subir un
 * archivo no es una acción por sí sola, es parte de lo que estás diciendo. */
export function Composer({
  busy,
  onSend,
}: {
  busy: boolean;
  onSend: (text: string, file: File | null) => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const canSend = !busy && (text.trim().length > 0 || file !== null);

  async function submit() {
    if (!canSend) return;
    const payload = { text: text.trim(), file };
    setText("");
    setFile(null);
    await onSend(payload.text, payload.file);
  }

  return (
    <div className="border-t border-bone-300 bg-bone-50 px-4 py-3">
      {file && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-full border border-bone-300 bg-bone-100 px-2.5 py-1 text-xs text-ink-700">
            <PaperclipIcon />
            {file.name}
            <button
              type="button"
              onClick={() => setFile(null)}
              className="ml-1 text-ink-300 hover:text-alert"
              aria-label="Quitar archivo"
            >
              ×
            </button>
          </span>
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        className="mx-auto flex max-w-3xl items-end gap-2 rounded-card border border-bone-300 bg-bone-50 px-2 py-1.5 focus-within:border-clay-500"
      >
        <button
          type="button"
          onClick={() => input.current?.click()}
          disabled={busy}
          title="Adjuntar un archivo"
          aria-label="Adjuntar un archivo"
          className="rounded p-1.5 text-ink-400 transition-colors hover:bg-bone-200 hover:text-ink-700 disabled:opacity-40"
        >
          <PaperclipIcon />
        </button>
        <input
          ref={input}
          type="file"
          accept=".csv,.xlsx,.xls,.txt,.tsv"
          className="hidden"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            event.target.value = "";
          }}
        />

        <textarea
          ref={box}
          value={text}
          rows={1}
          disabled={busy}
          onChange={(event) => {
            setText(event.target.value);
            const element = event.target;
            element.style.height = "auto";
            element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
          }}
          onKeyDown={(event) => {
            // Enter envía; Shift+Enter hace salto de línea, como en cualquier chat.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="Escribe un mensaje o adjunta una hoja de cálculo…"
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-sm text-ink-900 outline-none placeholder:text-ink-300 disabled:opacity-60"
        />

        <button
          type="submit"
          disabled={!canSend}
          aria-label="Enviar"
          className="rounded-md bg-clay-500 p-1.5 text-bone-50 transition-colors hover:bg-clay-600 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <SendIcon />
        </button>
      </form>
    </div>
  );
}
