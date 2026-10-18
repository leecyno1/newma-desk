import type { PolicyDocument } from "./types";

export function PolicyDocumentPanel({ document, reading, error, disabled, onRead }: {
  document?: PolicyDocument; reading: boolean; error?: string; disabled?: boolean; onRead(): void;
}) {
  const available = document?.status === "available";
  return <section className="policy-document" aria-label="官方正文证据">
    <header><h3>官方正文证据</h3><button type="button" disabled={reading || disabled} onClick={onRead}>
      {reading ? "正在读取官方正文…" : available ? "重新抓取正文" : "读取官方正文"}
    </button></header>
    {error ? <p className="document-error" role="alert">{error}{available ? " 已保存正文仍可查看，但本次获取失败。" : ""}</p> : null}
    {available ? <>
      <dl className="document-metadata">
        <div><dt>发文机关</dt><dd>{document.issuer || "正文未明确"}</dd></div>
        <div><dt>发文字号</dt><dd>{document.documentNumber || "未识别"}</dd></div>
        <div><dt>网页发布</dt><dd>{document.publishedAt || "未识别"}</dd></div>
        <div><dt>成文日期</dt><dd>{document.issuedAt || "未识别"}</dd></div>
        <div><dt>施行日期</dt><dd>{document.effectiveAt || "未明确，不默认视为已生效"}</dd></div>
        <div><dt>采集时间</dt><dd>{document.fetchedAt ? new Date(document.fetchedAt).toLocaleString("zh-CN") : "未知"}</dd></div>
      </dl>
      {document.effectiveDateQuote ? <blockquote>{document.effectiveDateQuote}</blockquote> : null}
      <p className="muted-note">正文记录 #{document.revision} · {document.text?.length ?? 0} 字 · {document.truncated ? "正文已截断，不能作完整全文对比" : document.note}</p>
      <details><summary>查看已保存的官方正文</summary><div className="document-text">{document.text}</div></details>
      {document.attachments?.length ? <div className="document-attachments">官方附件（未解析）：{document.attachments.map((item) => <a href={item.url} target="_blank" rel="noreferrer" key={item.url}>{item.title || "附件"}</a>)}</div> : null}
    </> : <p className="muted-note">尚无正文证据。摘要只供线索筛选，不能用于逐条对比、生效判断或确定性投资结论。</p>}
  </section>;
}
