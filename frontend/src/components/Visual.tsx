import ReactECharts from "echarts-for-react";
import type { VisualData, VisualSpec } from "../api/types";
import { buildOption, formatCell, formatNumber } from "../charts/options";

/** Pinta una visualizacion segun su tipo.
 *
 * KPI y tabla no son graficos: darles un canvas de ECharts seria disfrazar
 * texto de grafico. Se pintan como lo que son. */
export function Visual({ spec, data }: { spec: VisualSpec; data: VisualData }) {
  if (data.rows.length === 0) {
    return <Empty />;
  }
  if (spec.type === "kpi") {
    return <Kpi data={data} />;
  }
  if (spec.type === "table") {
    return <Table data={data} />;
  }
  return (
    <ReactECharts
      option={buildOption(spec, data)}
      style={{ height: "100%", width: "100%" }}
      opts={{ renderer: "svg" }}
      notMerge
    />
  );
}

function Kpi({ data }: { data: VisualData }) {
  const column = data.columns[0];
  const value = data.rows[0]?.[column.key];
  return (
    <div className="flex h-full flex-col items-start justify-center px-2">
      <span className="text-4xl font-semibold tracking-tight text-ink-900 tabular">
        {formatNumber(value)}
      </span>
      <span className="mt-1 text-xs text-ink-400">{column.label}</span>
    </div>
  );
}

function Table({ data }: { data: VisualData }) {
  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-bone-50">
          <tr>
            {data.columns.map((column) => (
              <th
                key={column.key}
                className="border-b border-bone-300 px-2 py-1.5 text-left text-xs font-medium text-ink-400"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, index) => (
            <tr key={index} className="border-b border-bone-200 last:border-0">
              {data.columns.map((column) => {
                const numeric = column.type === "integer" || column.type === "float";
                return (
                  <td
                    key={column.key}
                    className={`px-2 py-1.5 text-ink-700 ${numeric ? "text-right tabular" : ""}`}
                  >
                    {numeric ? formatNumber(row[column.key]) : formatCell(row[column.key])}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-ink-300">
      Sin datos para esta consulta
    </div>
  );
}
