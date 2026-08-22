import { Activity, AlertTriangle, BarChart3, RefreshCw, Shield, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { Bar, MarketDataSource, SecurityRef } from "../types";
import { formatPrice, movement, signed } from "./shared";

type TechnicalSnapshot = {
  close: number;
  changePct?: number;
  sma20?: number;
  sma60?: number;
  volatility?: number;
  drawdown?: number;
  support?: number;
  resistance?: number;
  volumeRatio?: number;
  regime: "uptrend" | "downtrend" | "range" | "unknown";
  evidence: string[];
  asOf?: string;
};

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : undefined;
}

function standardDeviation(values: number[]) {
  if (values.length < 2) return undefined;
  const mean = average(values);
  if (mean === undefined) return undefined;
  return Math.sqrt(values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / (values.length - 1));
}

function snapshot(bars: Bar[]): TechnicalSnapshot | undefined {
  const closes = bars.map((bar) => bar.close).filter(Number.isFinite);
  if (!closes.length) return undefined;
  const recent = closes.slice(-20);
  const medium = closes.slice(-60);
  const returns = closes.slice(1).map((value, index) => {
    const previous = closes[index];
    return previous ? (value / previous - 1) * 100 : undefined;
  }).filter((value): value is number => value !== undefined && Number.isFinite(value));
  const sma20 = average(recent);
  const sma60 = average(medium);
  const close = closes.at(-1)!;
  const high = Math.max(...medium);
  const low = Math.min(...medium);
  let peak = closes[0] ?? close;
  let maxDrawdown = 0;
  for (const value of closes) {
    peak = Math.max(peak, value);
    maxDrawdown = Math.min(maxDrawdown, (value / peak - 1) * 100);
  }
  const volumeRecent = bars.slice(-20).map((bar) => bar.volume ?? 0).filter(Number.isFinite);
  const volumePrior = bars.slice(-40, -20).map((bar) => bar.volume ?? 0).filter(Number.isFinite);
  const recentVolume = average(volumeRecent);
  const priorVolume = average(volumePrior);
  const volumeRatio = recentVolume !== undefined && priorVolume ? recentVolume / priorVolume : undefined;
  const regime = sma20 === undefined || sma60 === undefined
    ? "unknown"
    : close > sma20 && sma20 > sma60
      ? "uptrend"
      : close < sma20 && sma20 < sma60
        ? "downtrend"
        : "range";
  const evidence = [
    sma20 === undefined ? "20 日均线不可用" : close >= sma20 ? "收盘位于 20 日均线上方" : "收盘位于 20 日均线下方",
    sma60 === undefined ? "60 日均线不可用" : sma20 !== undefined && sma20 >= sma60 ? "短期均线高于 60 日均线" : "短期均线低于 60 日均线",
    volumeRatio === undefined ? "成交量对比不可用" : volumeRatio >= 1.2 ? "近 20 日平均成交量放大" : volumeRatio <= 0.8 ? "近 20 日平均成交量收缩" : "成交量接近前 20 日均值",
  ];
  return {
    close,
    changePct: closes.length > 1 ? (close / closes.at(-2)! - 1) * 100 : undefined,
    sma20,
    sma60,
    volatility: standardDeviation(returns),
    drawdown: maxDrawdown,
    support: low,
    resistance: high,
    volumeRatio,
    regime,
    evidence,
    asOf: bars.at(-1)?.timestamp ? new Date(bars.at(-1)!.timestamp).toISOString() : undefined,
  };
}

const REGIME_LABEL = { uptrend: "上行趋势", downtrend: "下行趋势", range: "震荡整理", unknown: "数据不足" } as const;

export function TechnicalAnalysisWorkspace({
  dataSource,
  security,
  refreshNonce,
  onContextChange,
}: {
  dataSource: MarketDataSource;
  security: SecurityRef;
  refreshNonce: number;
  onContextChange: (state: Record<string, unknown>) => void;
}) {
  const [state, setState] = useState<TechnicalSnapshot>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void dataSource.ohlcv(security, "1d", security.market === "CN" ? "qfq" : "none").then((result) => {
      if (!active) return;
      const next = snapshot(result.items);
      setState(next);
      onContextChange({
        workspace: "technical",
        source: result.source,
        asOf: result.asOf,
        regime: next?.regime ?? "unknown",
        indicators: next ? { sma20: next.sma20 ?? null, sma60: next.sma60 ?? null, volatility: next.volatility ?? null, drawdown: next.drawdown ?? null } : null,
      });
    }).catch((reason) => active && setError(reason instanceof Error ? reason.message : "技术分析数据暂不可用"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [dataSource, onContextChange, refreshNonce, security]);

  const title = state ? REGIME_LABEL[state.regime] : "等待数据";
  const movementClass = movement(state?.changePct);
  const evidence = useMemo(() => state?.evidence ?? [], [state?.evidence]);
  return (
    <div className="technical-workspace">
      <section className="technical-hero">
        <div className="workspace-section-title"><span><Activity size={15} />技术结构</span><small>{state?.asOf ? new Date(state.asOf).toLocaleDateString("zh-CN") : "等待日线"}</small></div>
        <div className="technical-regime-row"><div className={"technical-regime " + (state?.regime ?? "unknown")}><strong>{title}</strong><span>日线结构</span></div><div><strong>{formatPrice(state?.close)}</strong><span className={movementClass}>{signed(state?.changePct)}</span></div><p>结构分析基于当前返回的 OHLCV 样本，不是预测信号。</p></div>
      </section>
      <section className="technical-grid">
        <div className="technical-panel"><div className="workspace-section-title"><span><BarChart3 size={14} />趋势与波动</span></div><div className="technical-metrics"><div><span>MA20</span><strong>{formatPrice(state?.sma20)}</strong></div><div><span>MA60</span><strong>{formatPrice(state?.sma60)}</strong></div><div><span>日波动</span><strong>{state?.volatility === undefined ? "—" : state.volatility.toFixed(2) + "%"}</strong></div><div><span>最大回撤</span><strong className="down">{state?.drawdown === undefined ? "—" : state.drawdown.toFixed(2) + "%"}</strong></div></div></div>
        <div className="technical-panel"><div className="workspace-section-title"><span><Shield size={14} />关键价位</span></div><div className="technical-levels"><div><TrendingDown size={14} /><span>支撑区间低点</span><strong>{formatPrice(state?.support)}</strong></div><div><TrendingUp size={14} /><span>阻力区间高点</span><strong>{formatPrice(state?.resistance)}</strong></div><div><span>成交量比</span><strong>{state?.volumeRatio === undefined ? "—" : state.volumeRatio.toFixed(2) + "x"}</strong></div></div></div>
      </section>
      <section className="technical-panel technical-evidence"><div className="workspace-section-title"><span><AlertTriangle size={14} />证据与限制</span><small>{security.name} · 近 60 个交易日</small></div>{evidence.map((item) => <div key={item}>· {item}</div>)}<p>支撑、阻力采用样本区间极值；完整分型、笔、中枢请通过 CZSC 结构 Mod 查看。</p></section>
      {loading ? <div className="sentiment-loading"><RefreshCw className="spin" size={14} />正在读取日线数据…</div> : null}
      {error ? <div className="workspace-error-banner" role="alert">{error}</div> : null}
    </div>
  );
}
