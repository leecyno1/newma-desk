import { CandlestickChart, Check, Columns2, LayoutGrid } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { KLineChartPanel } from "@newma-desk/chart-kit";

import type {
  Adjustment,
  MarketDataSource,
  PrimaryIndicator,
  Quote,
  SecondaryIndicator,
  SecurityRef,
  Timeframe,
} from "../types";
import { formatCompact, formatPrice, movement, signed } from "./shared";
import type { WorkspaceUiAction } from "./WorkspaceApp";
import { ADJUSTMENT_LABELS, requestedAdjustment } from "./comparison";

type PanelEvidence = { adjustment: Adjustment | null; source: string | null; asOf: string | null; count: number; status: "loading" | "ready" | "empty" | "error" };

const PANELS: Array<{ timeframe: Timeframe; label: string; hint: string }> = [
  { timeframe: "1d", label: "日线", hint: "中期结构" },
  { timeframe: "60m", label: "60 分钟", hint: "波段节奏" },
  { timeframe: "15m", label: "15 分钟", hint: "短线结构" },
  { timeframe: "5m", label: "5 分钟", hint: "盘中变化" },
];

function TimeframeChart({
  dataSource,
  security,
  timeframe,
  label,
  hint,
  adjustment,
  primaryIndicator,
  secondaryIndicator,
  theme,
  refreshNonce,
  active,
  onActivate,
  crosshairSyncGroup,
  onEvidence,
}: {
  dataSource: MarketDataSource;
  security: SecurityRef;
  timeframe: Timeframe;
  label: string;
  hint: string;
  adjustment: Adjustment;
  primaryIndicator: PrimaryIndicator;
  secondaryIndicator: SecondaryIndicator;
  theme: "light" | "dark";
  refreshNonce: number;
  active: boolean;
  onActivate: () => void;
  crosshairSyncGroup: string;
  onEvidence: (timeframe: Timeframe, evidence: PanelEvidence) => void;
}) {
  const [loadState, setLoadState] = useState<{ loading: boolean; error?: string }>({ loading: true });
  const [evidence, setEvidence] = useState<PanelEvidence | null>(null);
  const request = useRef(0);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const loadBars = useCallback(
    async () => {
      const id = ++request.current;
      const report = (next: PanelEvidence) => {
        if (!mounted.current || id !== request.current) return;
        setEvidence(next);
        onEvidence(timeframe, next);
      };
      report({ adjustment: null, source: null, asOf: null, count: 0, status: "loading" });
      try {
        const result = await dataSource.ohlcv(security, timeframe, adjustment);
        report({ adjustment: result.adjust ?? null, source: result.source, asOf: result.asOf, count: result.items.length, status: result.items.length ? "ready" : "empty" });
        return result.items;
      } catch (error) {
        report({ adjustment: null, source: null, asOf: null, count: 0, status: "error" });
        throw error;
      }
    },
    [adjustment, dataSource, security, timeframe, onEvidence],
  );
  return (
    <section className="timeframe-panel" data-active={active} onPointerDown={onActivate}>
      <header>
        <span><CandlestickChart size={13} /><strong>{label}</strong><small>{hint}</small></span>
        <em>{loadState.loading ? "加载中" : loadState.error ? "数据异常" : evidence?.count ? <><Check size={12} />已同步</> : "暂无数据"}</em>
      </header>
      <div className="workspace-help">请求：{ADJUSTMENT_LABELS[adjustment]} · 返回：{evidence?.adjustment ? ADJUSTMENT_LABELS[evidence.adjustment] : "待确认"} · 来源：{evidence?.source ?? "待确认"}{evidence?.adjustment && evidence.adjustment !== adjustment ? " · 口径已降级，请复核" : ""}</div>
      <KLineChartPanel
        security={security}
        timeframe={timeframe}
        adjustment={adjustment}
        primaryIndicator={primaryIndicator}
        secondaryIndicator={secondaryIndicator}
        theme={theme}
        refreshNonce={refreshNonce}
        loadBars={loadBars}
        crosshairSyncGroup={crosshairSyncGroup}
        onLoadState={setLoadState}
        ariaLabel={`${label} K 线图`}
      />
    </section>
  );
}

export function MultiTimeframeWorkspace({
  action,
  dataSource,
  security,
  quote,
  theme,
  refreshNonce,
  onContextChange,
}: {
  action?: WorkspaceUiAction;
  dataSource: MarketDataSource;
  security: SecurityRef;
  quote?: Quote;
  theme: "light" | "dark";
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const [activeTimeframe, setActiveTimeframe] = useState<Timeframe>("1d");
  const [adjustment, setAdjustment] = useState<Adjustment>("qfq");
  const [primaryIndicator, setPrimaryIndicator] = useState<PrimaryIndicator>("MA");
  const [secondaryIndicator, setSecondaryIndicator] = useState<SecondaryIndicator>("VOL");
  const [compact, setCompact] = useState(false);
  const crosshairSyncGroup = `multi-timeframe:${security.market}:${security.symbol}`;
  const requestKey = `${crosshairSyncGroup}:${security.assetType ?? ""}:${adjustment}:${refreshNonce}`;
  const [panelResults, setPanelResults] = useState<{ key: string; values: Partial<Record<Timeframe, PanelEvidence>> }>({ key: "", values: {} });
  const onEvidence = useCallback((timeframe: Timeframe, evidence: PanelEvidence) => {
    setPanelResults((previous) => ({ key: requestKey, values: { ...(previous.key === requestKey ? previous.values : {}), [timeframe]: evidence } }));
  }, [requestKey]);

  useEffect(() => {
    if (!action) return;
    if (action.actionId === "market.set-timeframe") {
      const next = action.input.timeframe as Timeframe;
      if (PANELS.some((panel) => panel.timeframe === next)) {
        setActiveTimeframe(next);
        setCompact(true);
      }
    }
    if (action.actionId === "chart.set-indicator") {
      if (action.input.position === "primary") setPrimaryIndicator(action.input.indicator as PrimaryIndicator);
      if (action.input.position === "secondary") setSecondaryIndicator(action.input.indicator as SecondaryIndicator);
    }
  }, [action]);

  useEffect(() => {
    onContextChange({
      activeTimeframe,
      synchronizedTimeframes: PANELS.map((item) => item.timeframe),
      adjustment: panelResults.key === requestKey ? panelResults.values[activeTimeframe]?.adjustment ?? null : null,
      requestedDailyAdjustment: requestedAdjustment(security, "1d", adjustment),
      panels: PANELS.map((panel) => ({
        timeframe: panel.timeframe,
        requestedAdjustment: requestedAdjustment(security, panel.timeframe, adjustment),
        ...(panelResults.key === requestKey ? panelResults.values[panel.timeframe] : undefined),
      })),
      priceComparisonWarning: "分钟线不复权，与复权日线的绝对价格不可直接比较",
      primaryIndicator,
      secondaryIndicator,
      layout: compact ? "focus" : "grid",
    });
  }, [activeTimeframe, adjustment, compact, onContextChange, primaryIndicator, secondaryIndicator, panelResults, requestKey, security]);

  return (
    <div className="multi-workspace">
      <div className="workspace-control-strip">
        <div className="workspace-segment" role="group" aria-label="主图指标">
          {(["MA", "EMA", "BOLL"] as PrimaryIndicator[]).map((indicator) => (
            <button type="button" key={indicator} aria-pressed={primaryIndicator === indicator} onClick={() => setPrimaryIndicator(indicator)}>{indicator}</button>
          ))}
        </div>
        <div className="workspace-segment" role="group" aria-label="副图指标">
          {(["VOL", "MACD", "RSI", "KDJ"] as SecondaryIndicator[]).map((indicator) => (
            <button type="button" key={indicator} aria-pressed={secondaryIndicator === indicator} onClick={() => setSecondaryIndicator(indicator)}>{indicator}</button>
          ))}
        </div>
        <label>日线复权 <select aria-label="复权方式" value={requestedAdjustment(security, "1d", adjustment)} onChange={(event) => setAdjustment(event.target.value as Adjustment)} disabled={requestedAdjustment(security, "1d", "qfq") === "none"}>
          <option value="none">不复权</option><option value="qfq">前复权</option><option value="hfq">后复权</option>
        </select></label>
        <button type="button" className="workspace-layout-button" aria-pressed={compact} onClick={() => setCompact((value) => !value)}>
          {compact ? <LayoutGrid size={14} /> : <Columns2 size={14} />}{compact ? "四图布局" : "聚焦当前"}
        </button>
      </div>
      <div className="multi-main">
        <div className="timeframe-grid" data-compact={compact}>
          {PANELS.map((panel) => (
            <TimeframeChart
              key={`${requestKey}:${panel.timeframe}`}
              {...panel}
              dataSource={dataSource}
              security={security}
              adjustment={requestedAdjustment(security, panel.timeframe, adjustment)}
              onEvidence={onEvidence}
              primaryIndicator={primaryIndicator}
              secondaryIndicator={secondaryIndicator}
              theme={theme}
              refreshNonce={refreshNonce}
              active={activeTimeframe === panel.timeframe}
              onActivate={() => setActiveTimeframe(panel.timeframe)}
              crosshairSyncGroup={crosshairSyncGroup}
            />
          ))}
        </div>
        <aside className="multi-inspector">
          <div className="workspace-section-title"><span>行情检查器</span><small>{security.market}</small></div>
          <div className={`inspector-price ${movement(quote?.changePct)}`}>
            <strong>{formatPrice(quote?.price, security.market === "HK" ? 3 : 2)}</strong>
            <span>{signed(quote?.changePct)}</span>
          </div>
          <dl>
            <div><dt>今开</dt><dd>{formatPrice(quote?.open)}</dd></div>
            <div><dt>最高</dt><dd className="up">{formatPrice(quote?.high)}</dd></div>
            <div><dt>最低</dt><dd className="down">{formatPrice(quote?.low)}</dd></div>
            <div><dt>成交额</dt><dd>{formatCompact(quote?.amount)}</dd></div>
            <div><dt>PE / PB</dt><dd>{formatPrice(quote?.pe)} / {formatPrice(quote?.pb)}</dd></div>
            <div><dt>当前周期</dt><dd>{PANELS.find((item) => item.timeframe === activeTimeframe)?.label}</dd></div>
          </dl>
          <div className="inspector-note">
            <strong>联动状态</strong>
            <span>证券、指标和主题已同步；当前聚焦周期会进入 Newma Agent Context。</span>
            <span>复权选择仅适用于A股日线；分钟线固定不复权，不应直接比较两者的绝对价格。每图以返回口径为准。</span>
          </div>
        </aside>
      </div>
    </div>
  );
}
