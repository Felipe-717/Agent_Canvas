import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GridLayout } from "react-grid-layout";
import type { Layout, LayoutItem } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { api } from "../api/client";
import type { DashboardDetail } from "../api/types";
import { Card, IconButton } from "./Card";
import { HowItWorks } from "./HowItWorks";
import { GridIcon, TrashIcon } from "./Icons";
import { Visual } from "./Visual";

const GRID = { rowHeight: 44, margin: [16, 16] as [number, number] };

/** El panel: graficos guardados, recalculados al abrir.
 *
 * Ninguno de estos numeros estaba almacenado. Cada uno se ha calculado ahora
 * mismo a partir de la especificacion guardada y de los datos actuales. */
export function Board({
  detail,
  onChanged,
}: {
  detail: DashboardDetail;
  onChanged: () => void;
}) {
  const [width, setWidth] = useState(1000);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo<LayoutItem[]>(
    () =>
      detail.visuals.map((visual) => ({
        i: visual.id,
        x: visual.placement.x,
        y: visual.placement.y,
        w: visual.placement.width,
        h: visual.placement.height,
        minW: 3,
        minH: 4,
      })),
    [detail.visuals],
  );

  const persist = useCallback(
    (next: Layout) => {
      void api.saveLayout(
        detail.dashboard.id,
        next.map((item) => ({
          visual_id: item.i,
          placement: { x: item.x, y: item.y, width: item.w, height: item.h },
        })),
      );
    },
    [detail.dashboard.id],
  );

  if (detail.visuals.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
        <span className="text-ink-300">
          <GridIcon />
        </span>
        <p className="text-sm font-medium text-ink-500">El panel está vacío</p>
        <p className="max-w-xs text-xs text-ink-400">
          Crea un gráfico en Explorar y pulsa «Fijar» para traerlo aquí.
        </p>
      </div>
    );
  }

  return (
    <div ref={container} className="h-full overflow-auto p-6">
      <GridLayout
        width={width}
        layout={layout}
        gridConfig={{ cols: detail.grid_columns, ...GRID }}
        // Solo la cabecera arrastra: si no, no se podria usar el grafico.
        dragConfig={{ handle: ".card-drag-handle" }}
        // El guardado ocurre al soltar, no durante: una peticion por arrastre,
        // no una por pixel.
        onDragStop={(next) => persist(next)}
        onResizeStop={(next) => persist(next)}
      >
        {detail.visuals.map((visual) => (
          <div key={visual.id}>
            <Card
              dragHandle
              title={visual.spec.title}
              subtitle={visual.error ? undefined : visual.spec.type}
              footer={<HowItWorks code={visual.code} />}
              actions={
                <IconButton
                  label="Quitar del panel"
                  danger
                  onClick={async () => {
                    await api.removeVisual(detail.dashboard.id, visual.id);
                    onChanged();
                  }}
                >
                  <TrashIcon />
                </IconButton>
              }
            >
              {visual.data ? (
                <Visual spec={visual.spec} data={visual.data} />
              ) : (
                <Broken reason={visual.error ?? "No se pudo calcular"} />
              )}
            </Card>
          </div>
        ))}
      </GridLayout>
    </div>
  );
}

/** Un visual roto no tumba el panel: se explica en su sitio y los demas siguen. */
function Broken({ reason }: { reason: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 px-3 text-center">
      <p className="text-xs font-medium text-alert">No se pudo calcular</p>
      <p className="text-xs text-ink-400">{reason}</p>
    </div>
  );
}
