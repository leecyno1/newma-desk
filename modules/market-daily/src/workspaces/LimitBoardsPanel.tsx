import { useEffect, useState } from "react";
import type { LimitBoards, MarketDataSource } from "../types";
import { BoardFollowThrough } from "./BoardFollowThrough";

export type BoardState = { status: "loading" | "loaded" | "error"; data: LimitBoards | null; error?: string; selectedPool: "U" | "D" | "Z" | "previous" };
const format = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;
function time(value: string | null) {
  const raw = String(value || "").padStart(6, "0");
  return /^(?:[01]\d|2[0-3])[0-5]\d[0-5]\d$/.test(raw) && value ? `${raw.slice(0, 2)}:${raw.slice(2, 4)}:${raw.slice(4)}` : "—";
}

export function LimitBoardsPanel({ dataSource, refreshNonce, onChange }: {
  dataSource: Pick<MarketDataSource, "limitBoards">; refreshNonce: number; onChange: (state: BoardState) => void;
}) {
  const [pool, setPool] = useState<BoardState["selectedPool"]>("U");
  const [state, setState] = useState<Omit<BoardState, "selectedPool">>({ status: "loading", data: null });
  useEffect(() => {
    let active = true;
    setState({ status: "loading", data: null });
    void dataSource.limitBoards(refreshNonce > 0).then(data => {
      if (active) setState({ status: "loaded", data });
    }).catch(error => {
      if (active) setState({ status: "error", data: null, error: error instanceof Error ? error.message : "涨跌停名单读取失败" });
    });
    return () => { active = false; };
  }, [dataSource, refreshNonce]);
  useEffect(() => onChange({ ...state, selectedPool: pool }), [state, pool, onChange]);
  const data = state.data, summary = data?.current ? data.summary : null;
  const items = data?.current ? data.items.filter(item => item.kind === pool) : [];
  return <section className="sentiment-panel sentiment-history limit-boards" aria-label="涨跌停与连板研究">
    <div className="workspace-section-title"><span>涨跌停与连板 · 不含ST</span><small>{data?.current ? `${data.asOf} · 日终` : state.status === "loading" ? "读取中" : "数据未确认"}</small></div>
    {state.status === "loading" ? <p className="sentiment-note" role="status">正在核验最近两个交易日名单；旧计数与名单已撤下。</p> : null}
    {state.status === "error" ? <p className="workspace-error-banner" role="alert">{state.error}；旧名单与旧判断已撤下。</p> : null}
    {data && !data.current ? <p className="sentiment-note">{data.reason}；缺数不算零，不回退到更早日期冒充当天。</p> : null}
    <div className="sentiment-history-metrics">
      <div><span>收盘涨停 / 跌停</span><strong>{format(summary?.up)} / {format(summary?.down)}</strong><small>仅本来源非ST名单</small></div>
      <div><span>炸板 / 涨停中开板回封</span><strong>{format(summary?.broken)} / {format(summary?.reopenedUp)}</strong><small>两类分开，次数不当家数</small></div>
      <div><span>收盘封住 / 炸板占比</span><strong>{format(summary?.sealRatePct, "%")} / {format(summary?.breakRatePct, "%")}</strong><small>分母为互斥U与Z名单家数之和</small></div>
      <div><span>昨日涨停续封率</span><strong>{format(summary?.retentionRatePct, "%")}</strong><small>两日交集 {format(summary?.retainedUp)} / 昨日涨停 {format(summary?.previousUp)}</small></div>
    </div>
    {data?.current ? <>
      <p className="sentiment-note">对照日 {data.previousDate || "未核验"} · {data.previousStatus === "ready" ? "昨日名单已核验" : "昨日名单缺失，不计算续封率"} · 已知最高 {format(summary?.knownMaxBoards)} 板 · 连板数缺失 {format(summary?.unknownBoards)} 只</p>
      <div className="limit-board-ladder" aria-label="连板梯队">{data.ladder.map(tier => <span key={tier.boards}><strong>{tier.boards === 1 ? "首板" : `${tier.boards}板`}</strong> {tier.count} 只</span>)}{!data.ladder.length ? <span>无可核验连板层级，不默认首板</span> : null}</div>
      <div className="limit-board-tabs" role="group" aria-label="切换涨跌停名单">{([['U', '涨停名单'], ['Z', '炸板名单'], ['D', '跌停名单'], ['previous', '昨日涨停去向']] as const).map(([kind, label]) => <button key={kind} type="button" aria-pressed={pool === kind} onClick={() => setPool(kind)}>{label}</button>)}</div>
      {pool === "previous" ? <BoardFollowThrough tracking={data.tracking} /> : <div className="sentiment-history-table limit-board-table"><table><thead><tr><th>证券 / 代码</th><th>行业</th><th>连板数</th><th>{pool === "D" ? "开板次数" : "炸板次数"}</th><th>首次封板</th><th>最后封板</th></tr></thead><tbody>{items.map(item => <tr key={item.code}>
        <td>{item.name}<small>{item.code}</small></td><td>{item.industry}</td><td>{format(item.boards)}</td><td>{format(item.openTimes)}</td><td>{time(item.firstTime)}</td><td>{time(item.lastTime)}</td>
      </tr>)}</tbody></table>{!items.length ? <p className="sentiment-note">当日已核验来源名单中，该分类为0只。</p> : null}</div>}
    </> : null}
    {data ? <details className="sentiment-method"><summary>数据范围与分母说明</summary><p>{data.note}</p><p>{data.source} · 来源获取 {data.receivedAt || "未取得"}</p></details> : null}
  </section>;
}
