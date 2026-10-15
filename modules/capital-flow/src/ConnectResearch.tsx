import { useEffect, useState } from "react";
import type { ConnectResearchData, ConnectResearchWindow } from "./types";

export interface ConnectResearchState { data: ConnectResearchData | null; loading: boolean; error: string; days: 5 | 20 }

export function useConnectResearch(active: boolean, refreshKey: number) {
  const [data, setData] = useState<ConnectResearchData | null>(null);
  const [days, setDays] = useState<5 | 20>(20);
  const [loading, setLoading] = useState(active);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!active) { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError("");
    void (async () => {
      try {
        for (let batch = 0; batch < 6; batch++) {
          const response = await fetch(`/api/capital-flow/connect-research?refresh=${batch === 0 && refreshKey > 0}`, { signal: controller.signal });
          if (!response.ok) throw new Error(`跨境历史读取失败（${response.status}）`);
          const next: ConnectResearchData = await response.json();
          if (controller.signal.aborted) return;
          setData(next);
          if (!next.canContinue) break;
        }
      } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "跨境历史读取失败"); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => controller.abort();
  }, [active, refreshKey]);
  return { state: { data, loading, error, days } satisfies ConnectResearchState, setDays };
}

export function connectContext(state?: ConnectResearchState, compact = false) {
  if (!state) return null;
  const data = state.data;
  const pending = state.loading || !!state.error;
  const window = data?.windows[state.days];
  const withStatus = (side: ConnectResearchWindow) => ({ ...side, current: side.current && !pending,
    points: compact ? undefined : side.points, closedDays: compact ? undefined : side.closedDays,
    momentum: side.momentum ? { ...side.momentum, current: side.momentum.current && !pending,
      recent: { ...side.momentum.recent, current: side.momentum.recent.current && !pending },
      previous: { ...side.momentum.previous, current: side.momentum.previous.current && !pending } } : undefined });
  return { days: state.days, loading: state.loading, error: state.error,
    cutoff: data?.cutoff, source: data?.source, progress: data ? `${data.completed}/${data.expected}` : null,
    selectedWindow: window ? { northbound: withStatus(window.northbound), southbound: withStatus(window.southbound) } : null, snapshotOnly: pending,
    notes: data?.notes, failedDates: data?.failedDates };
}

const fmt = (value: number | null | undefined) => value == null ? "--" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

export function ConnectBrief({ state, open }: { state: ConnectResearchState; open: () => void }) {
  const selected = connectContext(state, true)?.selectedWindow;
  return <section className="connect-brief" aria-label="跨境资金总览研究">
    <div className="section-title"><h2>跨境资金 · {state.days}个通道交易日</h2><button type="button" onClick={open}>查看跨境证据 →</button></div>
    <p>HKEX逐日统计 · 各自通道日历，与A股权益窗口不一定同日起止；港元、人民币不相加。</p>
    {state.error && <p className="error-banner">{state.error} · 不用旧单日快照代替研究结论</p>}
    <div className="connect-brief-grid">{(["southbound", "northbound"] as const).map(side => {
      const south = side === "southbound", window = selected?.[side], summary = window?.summary, momentum = window?.momentum;
      return <button type="button" key={side} data-connect-brief={side} onClick={open}>
        <span>{south ? "南向净买入" : "北向成交额"} ↗</span>
        <strong>{fmt(south ? summary?.netBuyYi : summary?.turnoverYi)} <small>{south ? "亿港元" : "亿元人民币"}</small></strong>
        <small>{window?.start ?? "--"} → {window?.asOf ?? "--"} · {window?.available ?? 0}/{state.days}日</small>
        <em>{state.loading ? "正在读取，暂不确认" : window?.current ? "窗口数据齐备" : "未确认，核对缺口"}</em>
        <span className="connect-brief-insight">{south
          ? window?.current && summary?.streakDays != null ? `末端${summary.streakCensored ? "至少" : ""}${summary.streakDays}日${summary.streakDirection === "buy" ? "净买入" : summary.streakDirection === "sell" ? "净卖出" : "净额持平"}` : "连续方向待确认"
          : "仅代表成交活跃度，不是净流入"}</span>
        <small>{momentum?.current
          ? south ? `近5日较此前5日：净额变化 ${fmt(momentum.netChangeYi)} 亿港元；强度变化 ${fmt(momentum.intensityChangePp)} 个百分点`
            : `近5日成交 / 此前5日：${fmt(momentum.turnoverRatio)} 倍`
          : "相邻五日对照未确认"}</small>
        {!!window?.missingDates.length && <small>窗口缺口：{window.missingDates.join("、")}</small>}
      </button>;
    })}</div>
    <p>五日强度＝净买入÷成交额，仅做历史比较，不作收益预测；详细日期、休市依据与原始数据见跨境证据。</p>
  </section>;
}

function Momentum({ data, south, pending }: { data?: ConnectResearchWindow["momentum"]; south: boolean; pending: boolean }) {
  const confirmed = data?.current && !pending;
  const delta = confirmed ? data.intensityChangePp : null;
  const ratio = confirmed ? data.turnoverRatio : null;
  const direction = !confirmed ? "对照未确认" : south
    ? delta == null ? "无成交，强度不可计算" : Math.abs(delta) < 0.005 ? "净买入强度基本持平" : delta > 0 ? "净买入强度上升" : "净买入强度下降"
    : ratio == null ? "此前成交为零，不计算倍数" : Math.abs(ratio - 1) < 0.005 ? "成交活跃度基本持平" : ratio > 1 ? "成交活跃度上升" : "成交活跃度下降";
  return <div className="connect-momentum" role="group" aria-label={south ? "南向五日强弱对照" : "北向五日活跃度对照"}>
    <div className="section-title"><h3>近5日 vs 此前5日</h3><span>{direction}</span></div>
    <p>固定比较相邻两段通道交易日，与上方图表窗口独立。</p>
    <div className="turnover-history-table"><table><thead><tr><th>时段 / 日期</th><th>{south ? "净买入" : "成交额"}</th><th>{south ? "净买入 / 成交" : "日均成交"}</th></tr></thead>
      <tbody>{(["previous", "recent"] as const).map(key => {
        const part = data?.[key];
        return <tr key={key}><td>{key === "recent" ? "近5日" : "此前5日"}<small>{part?.start ?? "--"} → {part?.end ?? "--"}</small></td>
          <td>{fmt(south ? part?.netBuyYi : part?.turnoverYi)}</td><td>{south ? `${fmt(part?.netIntensityPct)}%` : fmt(part?.turnoverYi != null ? part.turnoverYi / 5 : null)}</td></tr>;
      })}</tbody></table></div>
    <p>{confirmed ? south
      ? `净买入变化 ${fmt(data.netChangeYi)} 亿港元 · 强度变化 ${fmt(delta)} 个百分点`
      : `两段成交比 ${fmt(ratio)} 倍（近5日 / 此前5日）`
      : `需两段各5日完整数据：近段 ${data?.recent.available ?? 0}/5、前段 ${data?.previous.available ?? 0}/5。${pending ? "正在读取或更新失败，已有数值仅为快照。" : "缺口不补零，不确认增强或减弱。"}`}</p>
    {!!data?.missingDates.length && <p>对照缺口：{data.missingDates.join("、")}</p>}
    <p>{south ? "强度＝区间净买入÷区间成交额；上升也可能只是净卖出收窄，不等于转为净买入，更不代表价格必涨。" : "成交放大可能来自双向换手，不能据此判断资金净流入。"}</p>
  </div>;
}

function HistorySide({ data, south, pending }: { data?: ConnectResearchWindow; south: boolean; pending: boolean }) {
  const metric = south ? "netBuyYi" : "turnoverYi";
  const points = data?.points ?? [];
  const max = Math.max(1, ...points.filter(row => row.status === "ready").map(row => Math.abs(row[metric] ?? 0)));
  const summary = data?.summary;
  const current = data?.current && !pending;
  return <section className="connect-research-side" aria-label={south ? "南向净买入研究" : "北向成交研究"}>
    <div className="section-title"><h2>{south ? "南向 · 买卖方向" : "北向 · 成交活跃度"}</h2><span>{data?.unit ?? (south ? "港元亿元" : "人民币亿元")}</span></div>
    <p>{data?.start ?? "--"} → {data?.asOf ?? "--"} · {data?.available ?? 0}/{data?.days ?? "--"}日可用 · {current ? "官方逐日数据齐备" : "待补齐 / 未确认"}</p>
    <div className="connect-research-metrics">
      <div><small>{south ? "窗口净买入" : "窗口累计成交"}</small><strong>{fmt(south ? summary?.netBuyYi : summary?.turnoverYi)}</strong></div>
      <div><small>{south ? "净买入天数" : "此前20日平均成交"}</small><strong>{south ? `${summary?.positiveDays ?? "--"} 天` : fmt(summary?.prior20MeanTurnoverYi)}</strong></div>
      <div><small>{south ? "窗口内连续方向" : "最新成交 / 前20日均值"}</small><strong>{south ? summary?.streakDays != null ? `${summary.streakCensored ? "至少" : ""}${summary.streakDays}日${summary.streakDirection === "buy" ? "买入" : summary.streakDirection === "sell" ? "卖出" : "持平"}` : "--" : `${fmt(summary?.latestVsPrior20)} 倍`}</strong></div>
    </div>
    {south && <p>买入 {fmt(summary?.buyYi)} · 卖出 {fmt(summary?.sellYi)} 港元亿元。净买入为买入减卖出，不等于外汇结算流量。</p>}
    <div className={`connect-research-chart ${south ? "signed" : ""}`} role="img" aria-label={south ? "南向逐日净买入" : "北向逐日成交额"}>{points.map(row => {
      const value = row.status === "ready" ? row[metric] : null;
      return <div key={row.date} title={`${row.date} · ${fmt(value)} ${data?.unit} · ${row.status === "ready" ? "官方数据" : "缺失或保留快照"}`}>
        {value == null ? <span>缺</span> : <i className={value >= 0 ? "in" : "out"} style={{ height: `${Math.abs(value) / max * (south ? 48 : 95)}%`, bottom: south ? value >= 0 ? "50%" : `${50 - Math.abs(value) / max * 48}%` : "0" }} />}
      </div>;
    })}</div>
    <p className="connect-chart-labels"><span>{points[0]?.date}</span><span>{south ? "零线上买入 / 线下卖出" : "成交额不是净流入"}</span><span>{points.at(-1)?.date}</span></p>
    {!!data?.missingDates.length && <p className="turnover-warning">缺口：{data.missingDates.join("、")}。缺口不作休市或零值处理。</p>}
    <Momentum data={data?.momentum} south={south} pending={pending} />
    <details><summary>逐日明细与休市依据</summary><div className="turnover-history-table"><table><thead><tr><th>日期</th><th>成交</th>{south && <><th>买入</th><th>卖出</th><th>净买入</th></>}<th>状态 / 原始数据</th></tr></thead><tbody>{points.map(row => <tr key={row.date}><td>{row.date}</td><td>{row.status === "ready" ? fmt(row.turnoverYi) : "--"}</td>{south && <><td>{row.status === "ready" ? fmt(row.buyYi) : "--"}</td><td>{row.status === "ready" ? fmt(row.sellYi) : "--"}</td><td>{row.status === "ready" ? fmt(row.netBuyYi) : "--"}</td></>}<td><a target="_blank" rel="noreferrer" href={`https://www.hkex.com.hk/chi/csm/DailyStat/data_tab_daily_${row.date.replaceAll("-", "")}c.js`}>{row.status === "ready" ? "HKEX ↗" : "待核验 ↗"}</a></td></tr>)}</tbody></table></div><p>45个日历日查询范围内官方休市：{data?.closedDays.join("、") || "尚未确认"}。周末不查询。</p></details>
  </section>;
}

export function ConnectResearch({ state, setDays }: ReturnType<typeof useConnectResearch>) {
  const window = state.data?.windows[state.days];
  return <section className="connect-research" aria-label="跨境资金历史研究">
    <div className="liquidity-masthead"><span>CONNECT / OFFICIAL EVIDENCE</span><p>南向看方向，北向看活跃度<span>币种分开 · 官方逐日核验</span></p></div>
    <div className="liquidity-toolbar"><span>历史截至 {state.data?.cutoff ?? "昨日"} · 日期覆盖 {state.data?.completed ?? 0}/{state.data?.expected ?? "--"}{state.loading ? " · 正在分批读取" : ""}</span><div className="research-period">{([5, 20] as const).map(days => <button type="button" key={days} aria-pressed={state.days === days} onClick={() => setDays(days)}>{days}个通道交易日</button>)}</div></div>
    {state.error && <p className="error-banner">{state.error} · 保留快照不代表更新成功</p>}
    {!!state.data?.failedDates.length && <p className="turnover-warning">读取失败：{state.data.failedDates.join("、")}；可使用页面刷新重试。</p>}
    <div className="connect-research-grid"><HistorySide data={window?.southbound} south pending={state.loading || !!state.error} /><HistorySide data={window?.northbound} south={false} pending={state.loading || !!state.error} /></div>
    <div className="evidence-note">{state.data?.notes.join(" ") ?? "直接读取港交所历史，未知日期不跳过，未披露的北向买卖方向不推算。"}</div>
  </section>;
}
