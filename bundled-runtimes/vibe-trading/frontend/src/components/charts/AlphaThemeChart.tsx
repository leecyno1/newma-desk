import { useEffect, useRef } from "react";
import { BarChart as EChartsBarChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import i18n from "@/i18n";
import type { AlphaBenchResult } from "@/lib/api";
import { getChartTheme } from "@/lib/chart-theme";
import { echarts } from "@/lib/echarts";
import { useDarkMode } from "@/hooks/useDarkMode";

echarts.use([
  EChartsBarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
]);

interface AlphaThemeChartProps {
  byTheme: AlphaBenchResult["by_theme"];
  height?: number;
}

export function AlphaThemeChart({ byTheme, height = 240 }: AlphaThemeChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const { dark, themeRevision } = useDarkMode();

  useEffect(() => {
    if (!chartRef.current) return;
    const theme = getChartTheme();
    const chart = echarts.init(chartRef.current);
    const themes = Object.keys(byTheme).sort();

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: {
        data: [i18n.t("alphaZoo.alive"), i18n.t("alphaZoo.reversed"), i18n.t("alphaZoo.dead")],
        textStyle: { color: theme.textColor, fontSize: 11 },
        right: 8,
        top: 4,
      },
      grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: themes.map((item) => i18n.t(`alphaZoo.themes.${item}`, { defaultValue: item })),
        axisLine: { lineStyle: { color: theme.axisColor } },
        axisLabel: { color: theme.textColor, fontSize: 10, rotate: themes.length > 6 ? 30 : 0 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: theme.gridColor } },
        axisLabel: { color: theme.textColor, fontSize: 10 },
      },
      series: [
        {
          name: i18n.t("alphaZoo.alive"),
          type: "bar",
          stack: "n",
          data: themes.map((item) => byTheme[item].alive),
          itemStyle: { color: theme.upColor },
        },
        {
          name: i18n.t("alphaZoo.reversed"),
          type: "bar",
          stack: "n",
          data: themes.map((item) => byTheme[item].reversed),
          itemStyle: { color: theme.warningColor },
        },
        {
          name: i18n.t("alphaZoo.dead"),
          type: "bar",
          stack: "n",
          data: themes.map((item) => byTheme[item].dead),
          itemStyle: { color: theme.downColor },
        },
      ],
    });

    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [byTheme, dark, themeRevision]);

  return <div ref={chartRef} style={{ height }} />;
}
