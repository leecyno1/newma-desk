import { Activity, BarChart3, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { MarketDataSource, MarketOverview, SecurityRef } from "../types";
import { formatCompact, movement, signed } from "./shared";

function ratio(up?: number, down?: number) {
  if (!Number.isFinite(up) || !Number.isFinite(down) || (up ?? 0) + (down ?? 0) <= 0) return undefined;
  return (up ?? 0) / ((up ?? 0) + (down ?? 0));
}

function tone(score?: number) {
  if (score === undefined) return "unknown";
  return score >= 0.66 ? "strong" : score >= 0.45 ? "balanced" : "weak";
}

export function SentimentWorkspace({
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
  const [overview, setOverview] = useState<MarketOverview>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    void dataSource.overview().then((next) => {
      if (!active) return;
      setOverview(next);
      const sentiment = next.sentiment;
      onContextChange({
        workspace: "sentiment",
        asOf: next.updated ?? null,
        breadth: { up: sentiment?.up ?? null, down: sentiment?.down ?? null, flat: sentiment?.flat ?? null },
        limitBoard: { up: sentiment?.zt ?? null, down: sentiment?.dt ?? null },
      });
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "市场情绪数据暂不可用");
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [dataSource, onContextChange, refreshNonce]);

  const sentiment = overview?.sentiment;
  const breadthRatio = ratio(sentiment?.up, sentiment?.down);
  const limitRatio = ratio(sentiment?.zt, sentiment?.dt);
  const score = breadthRatio === undefined && limitRatio === undefined
    ? undefined
    : ((breadthRatio ?? 0.5) * 0.7 + (limitRatio ?? 0.5) * 0.3);
  const label = score === undefined ? "等待数据" : score >= 0.72 ? "偏热" : score >= 0.55 ? "偏强" : score >= 0.42 ? "中性" : "偏弱";
  const sectors = useMemo(() => (overview?.sectors ?? []).slice(0, 12), [overview?.sectors]);

  return (
    <div className="sentiment-workspace">
      <section className="sentiment-hero">
        <div className="workspace-section-title"><span><Activity size={15} />市场情绪温度</span><small>{overview?.updated || "等待行情源"}</small></div>
        <div className="sentiment-score-row">
          <div className={"sentiment-score " + tone(score)}><strong>{score === undefined ? "—" : Math.round(score * 100)}</strong><span>{label}</span></div>
          <div className="sentiment-copy"><strong>{security.name} 所在市场的广度与涨停结构</strong><p>情绪分数只由当前数据源返回的市场统计计算，不代表涨跌预测。</p></div>
        </div>
        <div className="sentiment-meter"><span style={{ width: String(score === undefined ? 0 : score * 100) + "%" }} /></div>
      </section>

      <section className="sentiment-grid">
        <div className="sentiment-panel">
          <div className="workspace-section-title"><span><BarChart3 size={14} />市场宽度</span></div>
          <div className="sentiment-stats">
            <div><TrendingUp size={14} /><span>上涨</span><strong className="up">{sentiment?.up ?? "—"}</strong></div>
            <div><TrendingDown size={14} /><span>下跌</span><strong className="down">{sentiment?.down ?? "—"}</strong></div>
            <div><span>平盘</span><strong>{sentiment?.flat ?? "—"}</strong></div>
            <div><span>涨停 / 跌停</span><strong>{sentiment?.zt ?? "—"} / {sentiment?.dt ?? "—"}</strong></div>
          </div>
          {breadthRatio !== undefined ? <p className="sentiment-note">上涨占比 {Math.round(breadthRatio * 100)}% · {sentiment?.breadth || "宽度已计算"}</p> : <p className="empty-copy">市场宽度数据暂不可用</p>}
        </div>
        <div className="sentiment-panel">
          <div className="workspace-section-title"><span>行业扩散</span><small>{sectors.length ? String(sectors.length) + " 个行业" : "等待数据"}</small></div>
          <div className="sector-diffusion-list">
            {sectors.map((sector) => <div key={sector.name}><span>{sector.name}</span><strong className={movement(sector.pct)}>{signed(sector.pct)}</strong><em>{formatCompact(sector.net)}</em></div>)}
            {!sectors.length ? <p className="empty-copy">行业涨跌与资金数据暂不可用</p> : null}
          </div>
        </div>
      </section>
      {loading ? <div className="sentiment-loading"><RefreshCw className="spin" size={14} />正在读取市场情绪数据…</div> : null}
      {error ? <div className="workspace-error-banner" role="alert">{error}</div> : null}
    </div>
  );
}
