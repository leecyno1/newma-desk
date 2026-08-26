import { useEffect, useRef } from "react";
import { LineChart as EChartsLineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import type { EquityPoint } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { CHART_GROUP, connectCharts, echarts } from "@/lib/echarts";
import { useDarkMode } from "@/hooks/useDarkMode";

echarts.use([
  EChartsLineChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
]);

interface EquityChartOverlayProps {
  leftCurve: EquityPoint[];
  rightCurve: EquityPoint[];
  leftLabel: string;
  rightLabel: string;
}

export function EquityChartOverlay({
  leftCurve,
  rightCurve,
  leftLabel,
  rightLabel,
}: EquityChartOverlayProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { dark, themeRevision } = useDarkMode();

  useEffect(() => {
    if (!ref.current) return;
    if (leftCurve.length === 0 && rightCurve.length === 0) return;

    const theme = getChartTheme();
    const chart = echarts.init(ref.current);
    chart.group = CHART_GROUP;
    connectCharts();

    const dates = Array.from(new Set([
      ...leftCurve.map((point) => point.time),
      ...rightCurve.map((point) => point.time),
    ])).sort();
    const leftMap = new Map(leftCurve.map((point) => [point.time, Number(point.equity)]));
    const rightMap = new Map(rightCurve.map((point) => [point.time, Number(point.equity)]));
    const leftData = dates.map((date) => leftMap.get(date) ?? null);
    const rightData = dates.map((date) => rightMap.get(date) ?? null);
    const primaryColor = getComputedStyle(document.documentElement)
      .getPropertyValue("--chart-compare-a")
      .trim() || "#a87432";
    const secondaryColor = getComputedStyle(document.documentElement)
      .getPropertyValue("--chart-compare-b")
      .trim() || "#3f7667";

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.tooltipText, fontSize: 11 },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          if (!Array.isArray(params) || !params.length) return "";
          let html = `<b>${params[0].axisValue}</b>`;
          for (const point of params) {
            if (point.value == null) continue;
            html += `<br/>${point.marker} ${point.seriesName}: <b>${Number(point.value).toLocaleString()}</b>`;
          }
          return html;
        },
      },
      legend: {
        data: [leftLabel, rightLabel],
        textStyle: { color: theme.textColor, fontSize: 11 },
        right: 8,
        top: 4,
      },
      grid: { left: 8, right: 8, top: 36, bottom: 40, containLabel: true },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: theme.axisColor } },
        axisLabel: { color: theme.textColor, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: theme.gridColor } },
        axisLabel: { color: theme.textColor, fontSize: 10 },
      },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 20, bottom: 4 }],
      series: [
        {
          name: leftLabel,
          type: "line",
          data: leftData,
          smooth: false,
          symbol: "none",
          lineStyle: { color: primaryColor, width: 2 },
          connectNulls: true,
        },
        {
          name: rightLabel,
          type: "line",
          data: rightData,
          smooth: false,
          symbol: "none",
          lineStyle: { color: secondaryColor, width: 2 },
          connectNulls: true,
        },
      ],
    });

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(ref.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [leftCurve, rightCurve, leftLabel, rightLabel, dark, themeRevision]);

  if (leftCurve.length === 0 && rightCurve.length === 0) return null;
  return <div ref={ref} style={{ height: 320 }} />;
}
