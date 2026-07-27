import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import {
  dispose,
  init,
  type Chart,
  type Crosshair,
  type KLineData,
  type VisibleRange,
} from "klinecharts";

import type {
  Adjustment,
  Bar,
  ChartAnnotation,
  PrimaryIndicator,
  SecondaryIndicator,
  SecurityRef,
  Timeframe,
} from "./types";

export interface KLineChartPanelHandle {
  draw(name: "segment" | "horizontalStraightLine" | "fibonacciLine"): void;
  clearDrawings(): void;
  visibleRange(): VisibleRange | undefined;
}

export interface KLineChartPanelProps {
  security: SecurityRef;
  timeframe: Timeframe;
  adjustment: Adjustment;
  primaryIndicator: PrimaryIndicator;
  secondaryIndicator: SecondaryIndicator;
  theme: "light" | "dark";
  refreshNonce?: number;
  className?: string;
  ariaLabel?: string;
  loadBars: () => Promise<Bar[]>;
  annotations?: ChartAnnotation[];
  crosshairSyncGroup?: string;
  onRangeChange?(range: VisibleRange): void;
  onCrosshairChange?(crosshair: Crosshair): void;
  onLoadState?(state: { loading: boolean; error?: string }): void;
}

const crosshairGroups = new Map<string, Set<(crosshair: Crosshair) => void>>();

function subscribeCrosshair(group: string, handler: (crosshair: Crosshair) => void) {
  const handlers = crosshairGroups.get(group) ?? new Set();
  handlers.add(handler);
  crosshairGroups.set(group, handlers);
  return () => {
    handlers.delete(handler);
    if (handlers.size === 0) crosshairGroups.delete(group);
  };
}

function publishCrosshair(group: string, source: (crosshair: Crosshair) => void, crosshair: Crosshair) {
  for (const handler of crosshairGroups.get(group) ?? []) {
    if (handler !== source) handler(crosshair);
  }
}

function annotationStyles(tone: ChartAnnotation["tone"], dark: boolean) {
  const color = tone === "positive"
    ? "#dc2626"
    : tone === "negative"
      ? "#16a34a"
      : tone === "warning"
        ? "#d97706"
        : "#2563eb";
  return {
    line: { color, size: 1, style: "dashed" as const },
    text: {
      color: dark ? "#f8fafc" : "#ffffff",
      backgroundColor: color,
      borderColor: color,
      borderSize: 1,
      paddingLeft: 4,
      paddingRight: 4,
      paddingTop: 2,
      paddingBottom: 2,
    },
  };
}

function periodOf(timeframe: Timeframe) {
  const periods = {
    "1m": { type: "minute", span: 1 },
    "5m": { type: "minute", span: 5 },
    "15m": { type: "minute", span: 15 },
    "30m": { type: "minute", span: 30 },
    "60m": { type: "hour", span: 1 },
    "1d": { type: "day", span: 1 },
    "1w": { type: "week", span: 1 },
    "1M": { type: "month", span: 1 },
  } as const;
  return periods[timeframe];
}

function chartStyles(theme: "light" | "dark") {
  const dark = theme === "dark";
  return {
    grid: {
      horizontal: { color: dark ? "#263244" : "#e8edf3" },
      vertical: { color: dark ? "#263244" : "#eef2f6" },
    },
    candle: {
      bar: {
        upColor: "#dc2626",
        downColor: "#16a34a",
        noChangeColor: dark ? "#94a3b8" : "#64748b",
        upBorderColor: "#dc2626",
        downBorderColor: "#16a34a",
        noChangeBorderColor: dark ? "#94a3b8" : "#64748b",
        upWickColor: "#dc2626",
        downWickColor: "#16a34a",
        noChangeWickColor: dark ? "#94a3b8" : "#64748b",
      },
      priceMark: {
        high: { color: dark ? "#cbd5e1" : "#475569" },
        low: { color: dark ? "#cbd5e1" : "#475569" },
        last: {
          upColor: "#dc2626",
          downColor: "#16a34a",
          noChangeColor: dark ? "#94a3b8" : "#64748b",
        },
      },
    },
    xAxis: {
      axisLine: { color: dark ? "#334155" : "#d8e0e9" },
      tickText: { color: dark ? "#94a3b8" : "#64748b" },
      tickLine: { color: dark ? "#334155" : "#d8e0e9" },
    },
    yAxis: {
      axisLine: { color: dark ? "#334155" : "#d8e0e9" },
      tickText: { color: dark ? "#94a3b8" : "#64748b" },
      tickLine: { color: dark ? "#334155" : "#d8e0e9" },
    },
    separator: { color: dark ? "#334155" : "#d8e0e9" },
    crosshair: {
      horizontal: { line: { color: dark ? "#64748b" : "#94a3b8" } },
      vertical: { line: { color: dark ? "#64748b" : "#94a3b8" } },
    },
  };
}

export const KLineChartPanel = forwardRef<KLineChartPanelHandle, KLineChartPanelProps>(
  function KLineChartPanel(
    {
      security,
      timeframe,
      adjustment,
      primaryIndicator,
      secondaryIndicator,
      theme,
      refreshNonce,
      className,
      ariaLabel = "K 线图表",
      loadBars,
      annotations = [],
      crosshairSyncGroup,
      onRangeChange,
      onCrosshairChange,
      onLoadState,
    },
    ref,
  ) {
    const elementRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<Chart | null>(null);
    const loaderRef = useRef(loadBars);
    const stateRef = useRef({ onRangeChange, onCrosshairChange, onLoadState });
    loaderRef.current = loadBars;
    stateRef.current = { onRangeChange, onCrosshairChange, onLoadState };

    useImperativeHandle(ref, () => ({
      draw(name) {
        chartRef.current?.createOverlay({ name, groupId: "vibedesk-user-drawings" });
      },
      clearDrawings() {
        chartRef.current?.removeOverlay({ groupId: "vibedesk-user-drawings" });
      },
      visibleRange() {
        return chartRef.current?.getVisibleRange();
      },
    }), []);

    useEffect(() => {
      const element = elementRef.current;
      if (!element) return;
      const chart = init(element, {
        locale: "zh-CN",
        timezone: security.timezone || (security.market === "US" ? "America/New_York" : security.market === "HK" ? "Asia/Hong_Kong" : "Asia/Shanghai"),
        styles: chartStyles(theme),
      });
      if (!chart) return;
      chartRef.current = chart;
      chart.setDataLoader({
        async getBars({ callback }) {
          stateRef.current.onLoadState?.({ loading: true });
          try {
            const bars = await loaderRef.current();
            callback(bars as KLineData[], false);
            stateRef.current.onLoadState?.({ loading: false });
          } catch (reason) {
            callback([], false);
            stateRef.current.onLoadState?.({
              loading: false,
              error: reason instanceof Error ? reason.message : "K 线加载失败",
            });
          }
        },
      });
      const onVisibleRangeChange = () => {
        stateRef.current.onRangeChange?.(chart.getVisibleRange());
      };
      let applyingRemoteCrosshair = false;
      const applySyncedCrosshair = (crosshair: Crosshair) => {
        if (applyingRemoteCrosshair) return;
        applyingRemoteCrosshair = true;
        chart.executeAction("onCrosshairChange", {
          ...(crosshair.timestamp === undefined ? {} : { timestamp: crosshair.timestamp }),
          ...(crosshair.dataIndex === undefined ? {} : { dataIndex: crosshair.dataIndex }),
        });
        applyingRemoteCrosshair = false;
      };
      const removeCrosshairSync = crosshairSyncGroup
        ? subscribeCrosshair(crosshairSyncGroup, applySyncedCrosshair)
        : () => undefined;
      const onChartCrosshairChange = (value?: unknown) => {
        const crosshair = value && typeof value === "object" ? value as Crosshair : {};
        stateRef.current.onCrosshairChange?.(crosshair);
        if (crosshairSyncGroup && !applyingRemoteCrosshair) {
          publishCrosshair(crosshairSyncGroup, applySyncedCrosshair, crosshair);
        }
      };
      chart.subscribeAction("onVisibleRangeChange", onVisibleRangeChange);
      chart.subscribeAction("onCrosshairChange", onChartCrosshairChange);
      const observer = new ResizeObserver(() => chart.resize());
      observer.observe(element);
      return () => {
        observer.disconnect();
        removeCrosshairSync();
        chart.unsubscribeAction("onVisibleRangeChange", onVisibleRangeChange);
        chart.unsubscribeAction("onCrosshairChange", onChartCrosshairChange);
        dispose(chart);
        chartRef.current = null;
      };
    }, []);

    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      chart.removeOverlay({ groupId: "vibedesk-annotations" });
      if (!annotations.length) return;
      chart.createOverlay(annotations.map((annotation) => ({
        id: annotation.id,
        groupId: "vibedesk-annotations",
        name: "simpleAnnotation",
        lock: true,
        points: [{ timestamp: annotation.timestamp, value: annotation.value }],
        extendData: annotation.label,
        styles: annotationStyles(annotation.tone, theme === "dark"),
      })));
    }, [annotations, theme]);

    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      chart.setStyles(chartStyles(theme));
      chart.setTimezone(
        security.timezone || (security.market === "US" ? "America/New_York" : security.market === "HK" ? "Asia/Hong_Kong" : "Asia/Shanghai"),
      );
      chart.setSymbol({
        ticker: `${security.market}:${security.symbol}`,
        pricePrecision: security.market === "HK" ? 3 : 2,
        volumePrecision: 0,
      });
      chart.setPeriod(periodOf(timeframe));
      chart.removeIndicator();
      chart.createIndicator({ name: primaryIndicator, paneId: "candle_pane" }, true);
      chart.createIndicator(secondaryIndicator, false);
      chart.resetData();
    }, [adjustment, primaryIndicator, refreshNonce, secondaryIndicator, security, theme, timeframe]);

    return (
      <div
        ref={elementRef}
        className={className ? `kline-chart ${className}` : "kline-chart"}
        aria-label={ariaLabel}
      />
    );
  },
);
