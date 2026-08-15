/* Los mismos tonos que theme.css, accesibles desde JS.
 *
 * ECharts necesita valores literales, no variables CSS, asi que esta es la
 * unica duplicacion deliberada del sistema de color. Si cambia una, cambia la
 * otra. */

export const SERIES = [
  "#b85c38",
  "#4a5f6d",
  "#c9973f",
  "#6e7f62",
  "#8c6a5d",
  "#a8908c",
  "#5f7470",
  "#8a7449",
] as const;

export const INK = "#241f1b";
export const INK_MUTED = "#6b5f52";
export const INK_FAINT = "#a89a89";
export const PAPER = "#fdfbf7";
export const RULE = "#e3d7c5";
export const CLAY = "#b85c38";

export function seriesColor(index: number): string {
  return SERIES[index % SERIES.length];
}
