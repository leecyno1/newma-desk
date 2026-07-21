import type { MetricItem, TableColumn } from "@vibedesk/contracts";

type ValueFormat = NonNullable<MetricItem["format"] | TableColumn["format"]>;

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});
const currencyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatValue(value: unknown, format: ValueFormat = "text"): string {
  if (value === null || value === undefined || value === "") return "—";

  if (format === "text") return String(value);
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (format === "number") return numberFormatter.format(value);
  if (format === "currency") return currencyFormatter.format(value);

  return `${numberFormatter.format(value)}%`;
}
