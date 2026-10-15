import type { CapitalSupplyData, SupplyEvent, SupplyKind } from "./types";
import type { ReactNode } from "react";

export type SupplyFilter = "all" | SupplyKind;
export function visibleSupplyRows(data: CapitalSupplyData | null, filter: SupplyFilter, limit = 80): SupplyEvent[] {
  return (data?.feeds.filter(feed => filter === "all" || feed.id === filter).flatMap(feed => feed.items) ?? [])
    .sort((a, b) => (b.eventDate ?? "").localeCompare(a.eventDate ?? "") || (b.annDate ?? "").localeCompare(a.annDate ?? ""))
    .slice(0, limit);
}
const format = (value: number | null) => value == null ? "--" : value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });

export function supplyMetrics(data: CapitalSupplyData | null) {
  const available = (id: SupplyKind) => {
    const feed = data?.feeds.find(item => item.id === id);
    return feed && ["ready", "empty"].includes(feed.status) && !feed.usingSaved ? feed : null;
  };
  const unlocked = available("share_float");
  return { repurchaseReports: available("repurchase")?.count ?? null, holderReports: available("stk_holdertrade")?.count ?? null,
    upcomingUnlockRecords: unlocked ? unlocked.items.filter(item => !item.superseded && item.eventDate && item.eventDate > data!.asOf).length : null };
}

export function supplyReview(data: CapitalSupplyData | null) {
  if (!data) return [];
  const cutoff = new Date(`${data.asOf}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - 29);
  return data.feeds.map(feed => {
    let detail = "";
    if (!["ready", "empty"].includes(feed.status) || feed.usingSaved) {
      detail = `来源未完整更新，不能作供需排除判断。${feed.reason}`;
    } else if (feed.id === "share_float") {
      const next = feed.items.filter(item => !item.superseded && item.eventDate && item.eventDate > data.asOf)
        .sort((a, b) => a.eventDate!.localeCompare(b.eventDate!))[0];
      detail = next ? `最近待解禁 ${next.eventDate}，先核对股东限售条件、实际可流通数量及最新公告；不预设会卖出。`
        : "查询窗口未返回待解禁记录；这不能排除其他减持或供给风险。";
    } else if (feed.id === "repurchase") {
      const latest = [...feed.items].sort((a, b) => (b.annDate ?? "").localeCompare(a.annDate ?? ""))[0];
      detail = latest ? `最新公告 ${latest.annDate ?? "未知"}，来源阶段「${latest.progress}」。先核对方案、执行余额和期限，不能把累计披露当新增买盘。`
        : "近一年未返回回购披露，不能据此判断公司没有回购安排。";
    } else {
      const reductions = feed.items.filter(item => item.label === "减持" && item.annDate && item.annDate >= cutoff.toISOString().slice(0, 10));
      detail = `近30个自然日有 ${reductions.length} 条减持披露（按公告日）。核对发生区间、是否重复及是否存在未执行计划；不作为全部实际卖出统计。`;
    }
    return { id: feed.id, title: feed.label, detail };
  });
}

export function SupplyResearch({ data, loading, error, filter, setFilter, limit, setLimit, verify, verification }: {
  data: CapitalSupplyData | null; loading: boolean; error: string; filter: SupplyFilter;
  setFilter: (filter: SupplyFilter) => void; limit: number; setLimit: (limit: number) => void;
  verify: (row: SupplyEvent) => void; verification?: ReactNode;
}) {
  const rows = visibleSupplyRows(data, filter, limit);
  const matched = data?.feeds.filter(feed => filter === "all" || feed.id === filter).reduce((count, feed) => count + feed.count, 0) ?? 0;
  const metrics = supplyMetrics(data);
  return <section className="supply-research" aria-label="回购增减持与解禁证据">
    <div className="research-heading"><div><span>SUPPLY & DEMAND EVIDENCE</span><h2>回购 · 股东交易 · 解禁</h2></div><span>{loading ? "证据更新中" : "公告与发生日期分开"}</span></div>
    {error ? <p className="error-banner">{error}</p> : null}
    {!data ? <div className="table-empty">{loading ? "正在读取回购、股东增减持及未来解禁证据…" : "尚未取得供需证据，不能判断供给压力"}</div> : <>
      <div className="supply-metrics">
        <div><span>近一年回购披露</span><strong>{metrics.repurchaseReports ?? "--"}<small>条</small></strong><small>计划 / 进展分开 · 不合计累计金额</small></div>
        <div><span>近一年增减持披露</span><strong>{metrics.holderReports ?? "--"}<small>条</small></strong><small>区间可能重叠 · 不当作计划全量库</small></div>
        <div><span>未来90天解禁股东记录</span><strong>{metrics.upcomingUnlockRecords ?? "--"}<small>条</small></strong><small>剔除较早披露 · 不代表实际卖出</small></div>
      </div>
      <div className="supply-review" aria-label="供需核验重点">{supplyReview(data).map(item => <div key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></div>)}</div>
      {data.capacity && <div className="supply-capacity"><strong>20日成交容量</strong><span>平均 {format(data.capacity.averageVolumeWan)} 万股 / {format(data.capacity.averageTurnoverYi)} 亿元</span><span>截止 {data.capacity.expectedDate ?? "未知"} · 覆盖 {data.capacity.samples}/20 日</span><small>{data.capacity.reason || data.capacity.note}</small></div>}
      {verification}
      <div className="supply-toolbar"><div className="research-period" aria-label="供需证据类型">{([['all', '全部证据'], ['repurchase', '回购披露'], ['stk_holdertrade', '股东增减持'], ['share_float', '限售解禁']] as const).map(([id, label]) => <button key={id} type="button" aria-pressed={filter === id} onClick={() => { setFilter(id); setLimit(80); }}>{label}</button>)}</div><span>显示 {rows.length}/{matched} 条 · 公告截止 {data.window.announcementEnd}</span></div>
      <div className="supply-sources">{data.feeds.filter(feed => filter === "all" || feed.id === filter).map(feed => <div key={feed.id}>
        <a href={feed.sourceUrl} target="_blank" rel="noreferrer">{feed.label} · 接口说明 ↗</a>
        <span>{feed.usingSaved ? "保存历史 · 更新失败" : feed.status === "ready" ? "已取得披露" : feed.status === "empty" ? "查询成功 · 区间无记录" : feed.status === "partial" ? "覆盖不完整" : "来源不可用"} · {feed.reason || `最新公告 ${feed.asOf ?? "--"}`}</span>
      </div>)}</div>
      <div className="research-table-scroll"><table className="research-table supply-table"><thead><tr><th>发生 / 解禁日期</th><th>事件 / 主体</th><th>来源阶段 / 口径</th><th>数量 万股</th><th>比例 %</th><th>披露金额 亿元</th><th>核验记录</th></tr></thead><tbody>{rows.map(row => <tr key={row.id} className={row.superseded ? "supply-superseded" : ""}>
        <td>{row.eventDate ?? "--"}<small>公告 {row.annDate ?? "未知"}</small>{row.beginDate && <small>开始 {row.beginDate}</small>}{row.expiryDate && <small>方案到期 {row.expiryDate}</small>}</td>
        <td><strong>{row.label}</strong><small>{row.holder || data.symbol}</small></td>
        <td><span className={`supply-stage ${row.stage === "待解禁" ? "upcoming" : ""}`}>{row.superseded ? "旧披露 · 不重复计数" : row.stage}</span><small>{row.progress}</small></td>
        <td>{format(row.sharesWan)}{row.capacityDaysAt5Pct != null && <small>5%成交参与场景约 {format(row.capacityDaysAt5Pct)} 日<br />假设全部卖出，不是预测</small>}</td><td>{format(row.ratioPct)}{row.ratioPct != null && <small>{row.kind === "share_float" ? "占总股本" : "占流通股"}</small>}</td><td>{format(row.amountYi)}{row.amountYi != null && <small>不合计为净流入</small>}</td>
        <td><button type="button" className="verify-document" disabled={!row.annDate} onClick={() => verify(row)}>核验公告</button><details><summary>原始字段</summary><p>{row.note}</p><pre>{JSON.stringify(row.raw, null, 2)}</pre></details></td>
      </tr>)}</tbody></table></div>
      {!rows.length && <div className="table-empty compact">当前类型没有可显示记录；请结合来源状态判断，不能据此认定没有供需风险。</div>}
      {rows.length < matched && <button className="supply-more" type="button" onClick={() => setLimit(limit + 80)}>再显示80条</button>}
      <div className="evidence-note">解禁覆盖 {data.window.start} — {data.window.unlockEnd}。回购进展不等于新增买盘；股东减持与解禁不合并成一个“资金流出”数字。</div>
      <details className="research-details"><summary>投资判断边界与数据口径</summary>{data.notes.map(note => <p key={note}>{note}</p>)}<p>此处负责资金供需提示；公告原文与事件研究在公司模组继续核验，不重复做公司基本面分析。</p></details>
    </>}
  </section>;
}
