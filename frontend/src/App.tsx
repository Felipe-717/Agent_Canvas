import { useCallback, useEffect, useState } from "react";
import { api, ApiFailure } from "./api/client";
import type {
  Artifact,
  CanvasSummary,
  Conversation,
  DashboardDetail,
  Message,
} from "./api/types";
import { Board } from "./components/Board";
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";

type View = { kind: "chat" } | { kind: "canvas"; id: string };

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [canvases, setCanvases] = useState<CanvasSummary[]>([]);
  const [canvas, setCanvas] = useState<DashboardDetail | null>(null);
  const [view, setView] = useState<View>({ kind: "chat" });
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [offline, setOffline] = useState(false);

  const refreshCanvases = useCallback(async () => {
    setCanvases(await api.listCanvases());
  }, []);

  const openConversation = useCallback(async (id: string) => {
    setActive(id);
    setView({ kind: "chat" });
    setFailure(null);
    setMessages(await api.messages(id));
  }, []);

  const newConversation = useCallback(async () => {
    const conversation = await api.startConversation();
    setConversations((current) => [conversation, ...current]);
    setActive(conversation.id);
    setMessages([]);
    setView({ kind: "chat" });
    setFailure(null);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [existing] = await Promise.all([api.listConversations(), refreshCanvases()]);
        setConversations(existing);
        if (existing.length > 0) {
          await openConversation(existing[0].id);
        } else {
          await newConversation();
        }
      } catch {
        setOffline(true);
      }
    })();
  }, [openConversation, newConversation, refreshCanvases]);

  const send = useCallback(
    async (text: string, file: File | null) => {
      if (!active) return;
      setBusy(true);
      setFailure(null);
      // El mensaje propio aparece al instante; esperar al servidor para verlo
      // haría que escribir se sintiera lento.
      const pending: Message = {
        id: `pending-${Date.now()}`,
        role: "user",
        text,
        attachments: file ? [{ file_id: "pending", filename: file.name }] : [],
        artifacts: [],
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, pending]);
      try {
        const turn = await api.send(active, text, file);
        setMessages((current) => [
          ...current.filter((message) => message.id !== pending.id),
          turn.user_message,
          turn.assistant_message,
        ]);
        setConversations(await api.listConversations());
      } catch (error) {
        setMessages((current) => current.filter((message) => message.id !== pending.id));
        setFailure(error as ApiFailure);
      } finally {
        setBusy(false);
      }
    },
    [active],
  );

  const pin = useCallback(
    async (artifact: Artifact, canvasId: string | null, name: string) => {
      if (!artifact.spec) return;
      const target = canvasId ?? (await api.createCanvas(name)).id;
      await api.pin(target, artifact.dataset_id, artifact.spec);
      await refreshCanvases();
    },
    [refreshCanvases],
  );

  const openCanvas = useCallback(async (id: string) => {
    setCanvas(await api.openCanvas(id));
    setView({ kind: "canvas", id });
  }, []);

  const refreshCanvas = useCallback(async () => {
    if (view.kind !== "canvas") return;
    setCanvas(await api.openCanvas(view.id));
    await refreshCanvases();
  }, [view, refreshCanvases]);

  if (offline) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="max-w-sm text-center text-sm text-ink-500">
          No se pudo conectar con el servidor. ¿Está levantado el backend?
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full bg-bone-100">
      <Sidebar
        conversations={conversations}
        activeConversation={view.kind === "chat" ? active : null}
        canvases={canvases}
        activeCanvas={view.kind === "canvas" ? view.id : null}
        onOpenConversation={(id) => void openConversation(id)}
        onNewConversation={() => void newConversation()}
        onDeleteConversation={async (id) => {
          await api.deleteConversation(id);
          const rest = await api.listConversations();
          setConversations(rest);
          if (id === active) {
            if (rest.length > 0) await openConversation(rest[0].id);
            else await newConversation();
          }
        }}
        onOpenCanvas={(id) => void openCanvas(id)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-bone-300 bg-bone-50 px-4 py-2.5">
          <span className="text-sm font-semibold tracking-tight text-ink-900">
            {view.kind === "chat"
              ? conversations.find((c) => c.id === active)?.title ?? "AgentCanvas"
              : canvas?.dashboard.name}
          </span>
          {view.kind === "canvas" && (
            <button
              type="button"
              onClick={() => setView({ kind: "chat" })}
              className="rounded px-2 py-1 text-xs text-ink-400 transition-colors hover:bg-bone-200 hover:text-ink-900"
            >
              Volver al chat
            </button>
          )}
        </header>

        <div className="min-h-0 flex-1">
          {view.kind === "chat" ? (
            <Chat
              messages={messages}
              busy={busy}
              failure={failure}
              canvases={canvases}
              onSend={send}
              onPin={pin}
            />
          ) : canvas ? (
            <Board detail={canvas} onChanged={() => void refreshCanvas()} />
          ) : null}
        </div>
      </main>
    </div>
  );
}
