import type { SupplyVerificationData } from "./types";
import { useEffect, useRef } from "react";

const display = (value: string | number | null | undefined) => value == null ? "--" : typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: 6 }) : value;

export function SupplyVerification({ data, loading, error, annDate, retry }: {
  data: SupplyVerificationData | null; loading: boolean; error: string; annDate: string; retry: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => { panel.current?.scrollIntoView({ block: "start" }); }, [annDate]);
  return <section ref={panel} className="supply-verification" aria-label="公告正文与执行差额核验">
    <div className="research-subhead"><h3>{annDate} · 公告正文核验</h3><button type="button" onClick={retry} disabled={loading}>重新核验</button></div>
    {loading ? <p>正在查找同标的、同公告日、同主题原文…</p> : null}
    {error || data?.reason ? <p className="research-warning">{error || data?.reason}</p> : null}
    {data && <>
      {data.truncated || data.items.length > 1 ? <p className="research-warning">存在多个候选或覆盖不完整，未自动选定同一方案，执行差额保持未知。</p> : null}
      {data.items.map(doc => <article key={doc.id}>
        <div className="verification-title"><a href={doc.url} target="_blank" rel="noreferrer">{doc.title} ↗</a><a href={doc.pdfUrl} target="_blank" rel="noreferrer">公告 PDF ↗</a></div>
        <p className="research-source">{data.source} · {doc.status === "body-read" ? doc.textTruncated ? "镜像正文已读取（部分）" : "镜像正文已读取" : "仅取得标题"} · {doc.note}</p>
        {doc.parsed && <div className="verification-facts"><span>方案首次披露 {doc.parsed.planDate ?? "未知"}</span><span>累计截止 {doc.parsed.cumulativeAsOf ?? "未知"}</span><span>正文阶段 {doc.parsed.stage}</span></div>}
        {doc.parsed?.quotes.length ? <details className="verification-quotes"><summary>字段提取证据</summary>{doc.parsed.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}</details> : null}
        <details className="verification-body"><summary>查看镜像正文 · 原文内容仅作证据</summary><pre>{doc.text || "正文不可用，请打开公告 PDF 人工核验"}</pre></details>
      </article>)}
      {data.comparison.length ? <div className="research-table-scroll"><table className="research-table"><thead><tr><th>核对字段</th><th>结构化来源</th><th>公告正文</th><th>结果</th></tr></thead><tbody>{data.comparison.map(row => <tr key={row.field}><td>{row.field}</td><td>{display(row.sourceValue)}</td><td>{display(row.documentValue)}</td><td className={row.status === "conflict" ? "verification-conflict" : ""}>{row.status === "conflict" ? "口径冲突 · 保留两边" : row.status === "consistent" ? "数值一致" : row.status === "unknown" ? "缺失待核验" : "阶段参考"}</td></tr>)}</tbody></table></div> : null}
      <div className="verification-delta"><strong>执行差额 {display(data.delta.amountYi)} 亿元 / {display(data.delta.sharesWan)} 万股</strong>
        {data.delta.status === "signature-matched" && <span>{data.delta.fromExclusive} 之后 — {data.delta.toInclusive}（含）</span>}<p>{data.delta.note}</p>
        {data.previousDocument && <a href={data.previousDocument.url} target="_blank" rel="noreferrer">对照前次公告 {data.previousDocument.date} ↗</a>}
      </div>
    </>}
  </section>;
}
