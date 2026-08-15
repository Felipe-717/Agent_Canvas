import { useEffect, useRef } from "react";
import type { ApiFailure } from "../api/client";
import type { Artifact, CanvasSummary, Message } from "../api/types";
import { Bubble } from "./Bubble";
import { Composer } from "./Composer";

const OPENING = [
  "Adjunta un Excel y dime qué quieres ver",
  "¿Qué puedes hacer?",
  "Resume la estructura de este archivo",
];

export function Chat({
  messages,
  busy,
  activity,
  failure,
  canvases,
  onSend,
  onPin,
}: {
  messages: Message[];
  busy: boolean;
  activity: string | null;
  failure: ApiFailure | null;
  canvases: CanvasSummary[];
  onSend: (text: string, file: File | null) => Promise<void>;
  onPin: (artifact: Artifact, canvasId: string | null, name: string) => Promise<void>;
}) {
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy, activity]);

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.length === 0 && !busy && (
            <Welcome onPick={(text) => void onSend(text, null)} />
          )}

          {messages.map((message) => (
            <Bubble key={message.id} message={message} canvases={canvases} onPin={onPin} />
          ))}

          {busy && <Thinking activity={activity} />}

          {failure && (
            <div className="rounded-card border border-alert/30 bg-alert/5 px-3 py-2">
              <p className="text-sm text-alert">{failure.message}</p>
              {failure.problems.map((problem) => (
                <p key={problem} className="mt-0.5 text-xs text-ink-500">
                  {problem}
                </p>
              ))}
            </div>
          )}

          <div ref={bottom} />
        </div>
      </div>

      <Composer busy={busy} onSend={onSend} />
    </div>
  );
}

function Welcome({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mt-16 flex flex-col items-center gap-4 text-center">
      <h2 className="text-lg font-medium text-ink-900">¿En qué te ayudo?</h2>
      <p className="max-w-sm text-sm text-ink-400">
        Pregunta lo que quieras. Si adjuntas una hoja de cálculo, la leo aunque tenga
        varias pestañas o las cabeceras a mitad de página.
      </p>
      <div className="flex flex-wrap justify-center gap-1.5">
        {OPENING.map((text) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="rounded-full border border-bone-300 px-3 py-1.5 text-xs text-ink-500 transition-colors hover:border-clay-300 hover:text-clay-600"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Tres puntos que respiran.
 *
 * El agente puede tardar varios segundos explorando un archivo; sin señal de
 * vida, la espera se lee como que algo se ha roto. */
function Thinking({ activity }: { activity: string | null }) {
  return (
    <div className="flex items-center gap-2 px-1">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="h-1.5 w-1.5 rounded-full bg-ink-300"
          style={{
            animation: "pulse 1.2s ease-in-out infinite",
            animationDelay: `${index * 0.16}s`,
          }}
        />
      ))}
      {/* Lo que esta haciendo ahora mismo, no un mensaje generico. */}
      {activity && <span className="text-xs text-ink-400">{activity}</span>}
    </div>
  );
}
