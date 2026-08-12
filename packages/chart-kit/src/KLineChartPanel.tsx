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

interface ResolvedChartColors {
  grid: string;
  text: string;
  axis: string;
  up: string;
  down: string;
  warning: string;
  accent: string;
  accentContrast: string;
  surfaceRaised: string;
}

function cssColor(
  element: HTMLElement | null | undefined,
  name: string,
  fallback: string,
): string {
  if (!element) return fallback;
  const view = element?.ownerDocument.defaultView;
  const value = view?.getComputedStyle(element).getPropertyValue(name).trim();
  return value || fallback;
}

function chartColors(
  theme: "light" | "dark",
  element?: HTMLElement | null,
): ResolvedChartColors {
  const dark = theme === "dark";
  return {
    grid: cssColor(element, "--vibe-chart-grid", dark ? "#2a3931" : "#d8cdbb"),
    text: cssColor(element, "--vibe-chart-text", dark ? "#a8b4a5" : "#66766e"),
    axis: cssColor(element, "--vibe-chart-axis", dark ? "#405146" : "#b9aa90"),
    up: cssColor(element, "--vibe-chart-up", dark ? "#f87171" : "#dc2626"),
    down: cssColor(element, "--vibe-chart-down", dark ? "#4ade80" : "#16a34a"),
    warning: cssColor(element, "--vibe-warning", dark ? "#fbbf24" : "#a16207"),
    accent: cssColor(element, "--vibe-accent", dark ? "#c89a5a" : "#a87432"),
    accentContrast: cssColor(
      element,
      "--vibe-accent-contrast",
      dark ? "#102019" : "#173128",
    ),
    surfaceRaised: cssColor(
      element,
      "--vibe-surface-raised",
      dark ? "#1a2821" : "#fffaf1",
    ),
  };
}

function annotationStyles(
  tone: ChartAnnotation["tone"],
  theme: "light" | "dark",
  element?: HTMLElement | null,
) {
  const palette = chartColors(theme, element);
  const color = tone === "positive"
    ? palette.up
    : tone === "negative"
      ? palette.down
      : tone === "warning"
        ? palette.warning
        : palette.accent;
  return {
    line: { color, size: 1, style: "dashed" as const },
    text: {
      color:
        tone === undefined || tone === "info"
          ? palette.accentContrast
          : palette.surfaceRaised,
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

function chartStyles(theme: "light" | "dark", element?: HTMLElement | null) {
  const palette = chartColors(theme, element);
  return {
    grid: {
      horizontal: { color: palette.grid },
      vertical: { color: palette.grid },
    },
    candle: {
      bar: {
        upColor: palette.up,
        downColor: palette.down,
        noChangeColor: palette.text,
        upBorderColor: palette.up,
        downBorderColor: palette.down,
        noChangeBorderColor: palette.text,
        upWickColor: palette.up,
        downWickColor: palette.down,
        noChangeWickColor: palette.text,
      },
      priceMark: {
        high: { color: palette.text },
        low: { color: palette.text },
        last: {
          upColor: palette.up,
          downColor: palette.down,
          noChangeColor: palette.text,
        },
      },
    },
    xAxis: {
      axisLine: { color: palette.axis },
      tickText: { color: palette.text },
      tickLine: { color: palette.axis },
    },
    yAxis: {
      axisLine: { color: palette.axis },
      tickText: { color: palette.text },
      tickLine: { color: palette.axis },
    },
    separator: { color: palette.axis },
    crosshair: {
      horizontal: { line: { color: palette.text } },
      vertical: { line: { color: palette.text } },
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
        styles: chartStyles(theme, element),
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
        styles: annotationStyles(annotation.tone, theme, elementRef.current),
      })));
    }, [annotations, theme]);

    useEffect(() => {
      const chart = chartRef.current;
      if (!chart) return;
      chart.setStyles(chartStyles(theme, elementRef.current));
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
