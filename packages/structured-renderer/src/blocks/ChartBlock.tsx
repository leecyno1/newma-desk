import { BarChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  TransformComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { LabelLayout, UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/lib/core";

import type { ChartBlock as ChartBlockContract } from "@vibe-visualization/contracts";

import { resolvePath } from "../resolvePath";

interface ChartBlockProps {
  block: ChartBlockContract;
  data: unknown;
}

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
  TransformComponent,
  DataZoomComponent,
  LabelLayout,
  UniversalTransition,
  CanvasRenderer,
]);

function isChartOption(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function ChartBlock({ block, data }: ChartBlockProps) {
  const option = resolvePath(data, block.optionPath);

  return (
    <section className="vv-view-block vv-chart-block" data-block-id={block.id}>
      {block.title ? <h2>{block.title}</h2> : null}
      {isChartOption(option) ? (
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: block.height ?? 320 }}
        />
      ) : (
        <p className="vv-empty">—</p>
      )}
    </section>
  );
}
