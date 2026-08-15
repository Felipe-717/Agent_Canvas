/* De `VisualSpec` + `VisualData` a opciones de ECharts.
 *
 * El backend entrega los datos en formato largo: cuando hay `group_by`, cada
 * fila lleva su categoria en una columna en vez de haber una columna por serie.
 * Pivotar es trabajo de aqui, porque es aqui donde se sabe como quiere ECharts
 * que le den de comer.
 *
 * Este modulo no calcula nada de negocio: no suma, no filtra, no ordena. Todo
 * eso ya lo hizo el motor determinista. Aqui solo se decide como se ve.
 */

import type { EChartsOption } from "echarts";
import type { Cell, VisualData, VisualSpec } from "../api/types";
import { CLAY, INK, INK_FAINT, INK_MUTED, RULE, SERIES, seriesColor } from "./palette";

const AXIS_LABEL = { color: INK_MUTED, fontSize: 11 };

const BASE: EChartsOption = {
  color: [...SERIES],
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: INK },
  animationDuration: 320,
  grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "#fdfbf7",
    borderColor: RULE,
    borderWidth: 1,
    textStyle: { color: INK, fontSize: 12 },
    // Sin sombra dura: el tooltip es una nota sobre el papel, no una ventana.
    extraCssText: "box-shadow: 0 6px 24px rgba(36,31,27,0.12); border-radius: 8px;",
  },
};

export function buildOption(spec: VisualSpec, data: VisualData): EChartsOption {
  switch (spec.type) {
    case "pie":
      return pieOption(spec, data);
    case "scatter":
      return scatterOption(spec, data);
    case "box":
      return boxOption(spec, data);
    case "bar":
    case "line":
    case "area":
      return cartesianOption(spec, data);
    default:
      return BASE;
  }
}

/** Nombre legible de una columna del resultado. */
function labelOf(data: VisualData, key: string): string {
  return data.columns.find((column) => column.key === key)?.label ?? key;
}

function measureKeys(spec: VisualSpec, data: VisualData): string[] {
  const dimensions = new Set(
    [spec.x, spec.group_by].filter(Boolean).map((d) => dimensionKey(d!)),
  );
  return data.columns.map((c) => c.key).filter((key) => !dimensions.has(key));
}

function dimensionKey(dimension: { field: string; time_grain: string | null }): string {
  return dimension.time_grain ? `${dimension.field}_${dimension.time_grain}` : dimension.field;
}

function cartesianOption(spec: VisualSpec, data: VisualData): EChartsOption {
  const xKey = spec.x ? dimensionKey(spec.x) : "";
  const groupKey = spec.group_by ? dimensionKey(spec.group_by) : null;
  const measures = measureKeys(spec, data);
  const categories = distinct(data.rows.map((row) => row[xKey]));
  const area = spec.type === "area";
  const line = spec.type === "line" || area;

  // Con group_by hay una serie por categoria; sin el, una por medida.
  const series = groupKey
    ? distinct(data.rows.map((row) => row[groupKey])).map((group, index) => ({
        name: String(group ?? "—"),
        data: categories.map((category) => {
          const match = data.rows.find(
            (row) => row[xKey] === category && row[groupKey] === group,
          );
          // `null` y no 0: un hueco en los datos no es un valor cero, y ECharts
          // lo dibuja como discontinuidad en vez de como caida a suelo.
          return match ? match[measures[0]] : null;
        }),
        ...shape(line, area, index),
      }))
    : measures.map((measure, index) => ({
        name: labelOf(data, measure),
        data: categories.map(
          (category) => data.rows.find((row) => row[xKey] === category)?.[measure] ?? null,
        ),
        ...shape(line, area, index),
      }));

  return {
    ...BASE,
    legend:
      series.length > 1
        ? { top: 0, left: 0, icon: "roundRect", itemWidth: 8, itemHeight: 8, textStyle: AXIS_LABEL }
        : undefined,
    grid: { ...BASE.grid, top: series.length > 1 ? 34 : 12 },
    xAxis: {
      type: "category",
      data: categories.map(formatCell),
      axisLine: { lineStyle: { color: RULE } },
      axisTick: { show: false },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: RULE, type: "dashed" } },
      axisLabel: { ...AXIS_LABEL, formatter: compact },
    },
    series,
  } as EChartsOption;
}

function shape(line: boolean, area: boolean, index: number) {
  if (!line) {
    return {
      type: "bar" as const,
      barMaxWidth: 40,
      itemStyle: { color: seriesColor(index), borderRadius: [3, 3, 0, 0] },
    };
  }
  return {
    type: "line" as const,
    smooth: 0.25,
    symbol: "circle",
    symbolSize: 5,
    lineStyle: { width: 2, color: seriesColor(index) },
    itemStyle: { color: seriesColor(index) },
    areaStyle: area ? { color: seriesColor(index), opacity: 0.14 } : undefined,
  };
}

function pieOption(spec: VisualSpec, data: VisualData): EChartsOption {
  const nameKey = spec.x ? dimensionKey(spec.x) : "";
  const valueKey = measureKeys(spec, data)[0];
  return {
    ...BASE,
    tooltip: { ...BASE.tooltip, trigger: "item" },
    legend: { bottom: 0, icon: "roundRect", itemWidth: 8, itemHeight: 8, textStyle: AXIS_LABEL },
    series: [
      {
        type: "pie",
        // Anillo y no tarta llena: deja sitio al centro y se lee mejor.
        radius: ["45%", "68%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fdfbf7", borderWidth: 2 },
        label: { color: INK_MUTED, fontSize: 11 },
        data: data.rows.map((row) => ({
          name: String(row[nameKey] ?? "—"),
          value: Number(row[valueKey] ?? 0),
        })),
      },
    ],
  } as EChartsOption;
}

/** Cajas y bigotes.
 *
 * El backend ya ha calculado las cinco cifras por categoría; aquí solo se
 * ordenan como ECharts las quiere: [mínimo, Q1, mediana, Q3, máximo]. */
function boxOption(spec: VisualSpec, data: VisualData): EChartsOption {
  const nameKey = spec.x ? dimensionKey(spec.x) : "";
  const orden = ["minimo", "q1", "mediana", "q3", "maximo"] as const;
  const etiquetas: Record<string, string> = {
    minimo: "mínimo",
    q1: "Q1",
    mediana: "mediana",
    q3: "Q3",
    maximo: "máximo",
  };

  return {
    ...BASE,
    tooltip: {
      ...BASE.tooltip,
      trigger: "item",
      formatter: (parametros: { name: string; value: number[] }) => {
        const [, min, q1, mediana, q3, max] = parametros.value;
        const filas = [min, q1, mediana, q3, max]
          .map((valor, indice) => `${etiquetas[orden[indice]]}: ${compact(valor)}`)
          .join("<br>");
        return `<b>${parametros.name}</b><br>${filas}`;
      },
    },
    xAxis: {
      type: "category",
      data: data.rows.map((row) => formatCell(row[nameKey])),
      axisLine: { lineStyle: { color: RULE } },
      axisTick: { show: false },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: RULE, type: "dashed" } },
      axisLabel: { ...AXIS_LABEL, formatter: compact },
    },
    series: [
      {
        type: "boxplot",
        data: data.rows.map((row) => orden.map((key) => Number(row[key] ?? 0))),
        itemStyle: { color: "#fdfbf7", borderColor: seriesColor(0), borderWidth: 1.5 },
        // La mediana en el color de acento: es la cifra que se lee primero.
        emphasis: { itemStyle: { borderColor: CLAY, borderWidth: 2 } },
        boxWidth: [10, 46],
      },
    ],
  } as EChartsOption;
}

function scatterOption(spec: VisualSpec, data: VisualData): EChartsOption {
  const xKey = spec.x ? dimensionKey(spec.x) : "";
  const groupKey = spec.group_by ? dimensionKey(spec.group_by) : null;
  const yKey = measureKeys(spec, data).filter((key) => key !== groupKey)[0];

  // Con `group_by`, una serie por categoría. Ignorarlo pintaba todos los
  // puntos del mismo color: un gráfico que parece correcto y no lo es.
  const grupos = groupKey ? distinct(data.rows.map((row) => row[groupKey])) : [null];
  const series = grupos.map((grupo, index) => ({
    type: "scatter" as const,
    name: grupo === null ? labelOf(data, yKey) : String(grupo ?? "—"),
    symbolSize: 9,
    itemStyle: { color: seriesColor(index), opacity: 0.75 },
    data: data.rows
      .filter((row) => groupKey === null || row[groupKey] === grupo)
      .map((row) => [Number(row[xKey] ?? 0), Number(row[yKey] ?? 0)]),
  }));

  return {
    ...BASE,
    tooltip: { ...BASE.tooltip, trigger: "item" },
    legend:
      grupos.length > 1
        ? { top: 0, left: 0, icon: "circle", itemWidth: 8, itemHeight: 8, textStyle: AXIS_LABEL }
        : undefined,
    grid: { ...BASE.grid, top: grupos.length > 1 ? 34 : 12 },
    xAxis: {
      type: "value",
      name: labelOf(data, xKey),
      nameTextStyle: AXIS_LABEL,
      splitLine: { lineStyle: { color: RULE, type: "dashed" } },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: "value",
      name: labelOf(data, yKey),
      nameTextStyle: AXIS_LABEL,
      splitLine: { lineStyle: { color: RULE, type: "dashed" } },
      axisLabel: { ...AXIS_LABEL, formatter: compact },
    },
    series,
  } as EChartsOption;
}

function distinct(values: Cell[]): Cell[] {
  return [...new Set(values.map((value) => JSON.stringify(value)))].map(
    (value) => JSON.parse(value) as Cell,
  );
}

/** Fechas ISO acortadas; el resto tal cual. */
export function formatCell(value: Cell): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value)) {
    return value.slice(0, 10);
  }
  return String(value);
}

export function compact(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (magnitude >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(Math.round(value * 100) / 100);
}

export function formatNumber(value: Cell): string {
  if (typeof value !== "number") return formatCell(value);
  return value.toLocaleString("es-ES", { maximumFractionDigits: 2 });
}

export { INK_FAINT };
