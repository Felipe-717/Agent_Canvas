import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { DashboardDetail, Dataset, VisualResult } from "./api/types";
import { Board } from "./components/Board";
import { DataPanel } from "./components/DataPanel";
import { Explore } from "./components/Explore";
import { ChartIcon, GridIcon } from "./components/Icons";

type Tab = "explore" | "board";

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [dashboard, setDashboard] = useState<DashboardDetail | null>(null);
  const [tab, setTab] = useState<Tab>("explore");
  const [failure, setFailure] = useState<string | null>(null);

  const loadDatasets = useCallback(async () => {
    const list = await api.listDatasets();
    setDatasets(list);
    // Mantiene fresco el dataset seleccionado tras subir un archivo nuevo:
    // su recuento de filas y su version activa acaban de cambiar.
    setSelected((current) => (current ? (list.find((d) => d.id === current.id) ?? null) : null));
  }, []);

  const loadDashboard = useCallback(async () => {
    const existing = await api.listDashboards();
    const summary = existing[0] ?? (await api.createDashboard("Mi panel"));
    setDashboard(await api.openDashboard(summary.id));
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await loadDatasets();
        await loadDashboard();
      } catch {
        setFailure("No se pudo conectar con el servidor. ¿Está levantado el backend?");
      }
    })();
  }, [loadDatasets, loadDashboard]);

  const pin = useCallback(
    async (result: VisualResult) => {
      if (!dashboard || !selected) return;
      await api.addVisual(dashboard.dashboard.id, selected.id, result.spec);
      setDashboard(await api.openDashboard(dashboard.dashboard.id));
    },
    [dashboard, selected],
  );

  const refreshBoard = useCallback(async () => {
    if (!dashboard) return;
    setDashboard(await api.openDashboard(dashboard.dashboard.id));
  }, [dashboard]);

  if (failure) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="max-w-sm text-center text-sm text-ink-500">{failure}</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-bone-100">
      <header className="flex items-center justify-between border-b border-bone-300 bg-bone-50 px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold tracking-tight text-ink-900">AgentCanvas</span>
          <span className="text-xs text-ink-300">datos en lenguaje natural</span>
        </div>
        <nav className="flex gap-1">
          <TabButton active={tab === "explore"} onClick={() => setTab("explore")} label="Explorar">
            <ChartIcon />
          </TabButton>
          <TabButton
            active={tab === "board"}
            onClick={() => {
              setTab("board");
              // Se recalcula al entrar: puede haber llegado un archivo nuevo.
              void refreshBoard();
            }}
            label="Panel"
          >
            <GridIcon />
          </TabButton>
        </nav>
      </header>

      <div className="flex min-h-0 flex-1">
        <DataPanel
          datasets={datasets}
          selected={selected}
          onSelect={(dataset) => {
            setSelected(dataset);
            // Elegir un conjunto de datos es querer preguntarle algo. Sin esto,
            // subir un archivo desde la pestana del panel no produce ningun
            // cambio visible donde el usuario esta mirando.
            setTab("explore");
          }}
          onChanged={() => {
            void loadDatasets();
            void refreshBoard();
          }}
        />
        <main className="min-w-0 flex-1">
          {tab === "explore" ? (
            <Explore dataset={selected} onPin={pin} />
          ) : dashboard ? (
            <Board detail={dashboard} onChanged={refreshBoard} />
          ) : null}
        </main>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
  children,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-bone-200 text-ink-900"
          : "text-ink-400 hover:bg-bone-100 hover:text-ink-700"
      }`}
    >
      {children}
      {label}
    </button>
  );
}
