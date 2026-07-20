import ReactECharts from "echarts-for-react";

import type { ChartBlock as ChartBlockContract } from "@vibe-visualization/contracts";

import { resolvePath } from "../resolvePath";

interface ChartBlockProps {
  block: ChartBlockContract;
  data: unknown;
}

function isChartOption(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function ChartBlock({ block, data }: ChartBlockProps) {
  const option = resolvePath(data, block.optionPath);

  return (
    <section className="vv-view-block vv-chart-block" data-block-id={block.id}>
      {block.title ? <h2>{block.title}</h2> : null}
      {isChartOption(option) ? (
        <ReactECharts option={option} style={{ height: block.height ?? 320 }} />
      ) : (
        <p className="vv-empty">—</p>
      )}
    </section>
  );
}
