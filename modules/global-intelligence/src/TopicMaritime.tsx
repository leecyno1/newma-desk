import { Anchor, ExternalLink } from "lucide-react";

export interface MaritimeEvidence {
  status: string;
  reason: string;
  source: string;
  sourceUrl: string;
  collectedAt: string | null;
  cacheExpiresAt: string | null;
  scannedCount: number | null;
  matchedCount: number | null;
  counts: Record<string, number> | null;
  selectionRule: string;
  limitations: string;
  warnings: Array<{
    id: string; reference: string; title: string; text: string; textTruncated: boolean;
    publishedAt: string | null; publicationDateRaw: string | null;
    scope: string; scopeLabel: string; authority: string | null; sourceUrl: string;
    status: string; currentValidity: string;
  }>;
}

export const MARITIME_SCOPES = {
  all: "全部",
  "hormuz-mentioned": "明确提及霍尔木兹",
  "nearby-coordinate": "附近坐标",
  regional: "区域公告",
} as const;

export interface MaritimeFilters {
  scope: keyof typeof MARITIME_SCOPES;
  query: string;
  sort: "relevance" | "newest";
  selectedId: string | null;
}

export const DEFAULT_MARITIME_FILTERS: MaritimeFilters = { scope: "all", query: "", sort: "relevance", selectedId: null };

export function buildMaritimeView(evidence: MaritimeEvidence, filters: MaritimeFilters) {
  const query = filters.query.trim().toLowerCase();
  const warnings = evidence.warnings.filter((warning) =>
    (filters.scope === "all" || warning.scope === filters.scope)
    && (!query || [warning.reference, warning.text, warning.title, warning.authority].join(" ").toLowerCase().includes(query)),
  );
  if (filters.sort === "newest") warnings.sort((a, b) => (b.publishedAt ?? "").localeCompare(a.publishedAt ?? ""));
  return {
    scope: filters.scope, query: filters.query, sort: filters.sort,
    filterCoverage: "loaded-records-only" as const,
    loadedCount: evidence.warnings.length,
    matchedCount: evidence.matchedCount,
    visibleWarningIds: warnings.map((warning) => warning.id),
    selectedWarning: warnings.find((warning) => warning.id === filters.selectedId) ?? null,
  };
}

export type MaritimeView = ReturnType<typeof buildMaritimeView>;

function utcTime(value: string | null) {
  const time = value ? Date.parse(value) : NaN;
  return Number.isFinite(time) ? `${new Date(time).toISOString().slice(0, 16).replace("T", " ")} UTC` : "时间未知";
}

export function TopicMaritime({ evidence, view, onChange }: {
  evidence: MaritimeEvidence;
  view: MaritimeView;
  onChange(filters: MaritimeFilters): void;
}) {
  const visibleWarnings = view.visibleWarningIds.map((id) => evidence.warnings.find((warning) => warning.id === id)!);
  const filtered = view.scope !== "all" || view.query !== "" || view.sort !== "relevance";
  const setFilters = (changes: Partial<MaritimeFilters>) => onChange({
    scope: view.scope, query: view.query, sort: view.sort, selectedId: null, ...changes,
  });
  return <section className="topic-panel topic-maritime" aria-label="霍尔木兹与周边航行警告">
    <header><span><Anchor size={15} />霍尔木兹与周边航行警告</span><a href={evidence.sourceUrl} target="_blank" rel="noreferrer">NGA 官方源 <ExternalLink size={12} /></a></header>
    <div className="topic-maritime-meta">
      <strong>{evidence.status === "ready" ? "已读取来源快照" : evidence.status === "stale" ? "旧快照 · 当前有效性待核验" : "来源暂不可用"}</strong>
      {evidence.collectedAt ? <span>最近成功采集 {utcTime(evidence.collectedAt)}</span> : null}
      {evidence.scannedCount !== null ? <span>已筛查 {evidence.scannedCount} 条 · 匹配 {evidence.matchedCount} 条 · 已载入 {evidence.warnings.length} 条</span> : null}
    </div>
    {evidence.reason ? <p className="topic-maritime-notice">{evidence.reason}</p> : null}
    {evidence.counts ? <p className="topic-maritime-counts">明确提及霍尔木兹 {evidence.counts["hormuz-mentioned"]} · 附近坐标线索 {evidence.counts["nearby-coordinate"]} · 区域性公告 {evidence.counts.regional}</p> : null}
    {evidence.warnings.length ? <div className="topic-maritime-controls">
      <div className="topic-maritime-scopes" role="group" aria-label="警告范围">
        {Object.entries(MARITIME_SCOPES).map(([scope, label]) => <button key={scope} type="button" aria-pressed={view.scope === scope} onClick={() => setFilters({ scope: scope as MaritimeFilters["scope"] })}>{label}</button>)}
      </div>
      <div className="topic-maritime-search">
        <input aria-label="警告关键词" placeholder="搜索编号、正文或发布机构" maxLength={120} value={view.query} onChange={(event) => setFilters({ query: event.target.value })} />
        <select aria-label="警告排序" value={view.sort} onChange={(event) => setFilters({ sort: event.target.value as MaritimeFilters["sort"] })}>
          <option value="relevance">相关性优先</option><option value="newest">最新发布</option>
        </select>
        {filtered ? <button type="button" onClick={() => onChange(DEFAULT_MARITIME_FILTERS)}>清除筛选</button> : null}
      </div>
      <span className="topic-maritime-filter-count" role="status">当前显示 {visibleWarnings.length} / 已载入 {evidence.warnings.length} 条；筛选仅针对已载入记录{(evidence.matchedCount ?? 0) > evidence.warnings.length ? "，未载入部分请在官方源核对" : ""}。</span>
      {view.selectedWarning ? <span className="topic-maritime-reading">当前阅读：{view.selectedWarning.reference} · 提问时携带此公告</span> : null}
    </div> : null}
    {!evidence.warnings.length ? <p className="topic-empty">{evidence.scannedCount === null ? "未获得可用警告数据，不能判断当前是否有警告。" : "本次快照未匹配到相关记录，不代表海峡安全或没有警告。"}</p> : <div className="topic-maritime-list" role="region" aria-label="匹配的航行警告" tabIndex={0}>
      {!visibleWarnings.length ? <p className="topic-empty">当前筛选在已载入记录中没有匹配，不代表来源没有相关警告。</p> : null}
      {visibleWarnings.map((warning) => <article key={warning.id} data-selected={view.selectedWarning?.id === warning.id || undefined}>
        <div className="topic-maritime-row-meta"><span>{warning.scopeLabel}</span><time>发布 {utcTime(warning.publishedAt)}</time></div>
        <details open={view.selectedWarning?.id === warning.id}>
          <summary onClick={(event) => {
            event.preventDefault();
            setFilters({ selectedId: view.selectedWarning?.id === warning.id ? null : warning.id });
          }}><strong>{warning.reference}</strong> · {warning.title}</summary>
          <pre>{warning.text}</pre>
          {warning.textTruncated ? <p>正文较长，已截取前 6000 字；请在官方源按编号查看完整公告。</p> : null}
          <p>原始发布日期：{warning.publicationDateRaw || "未知"} · 发布依据：{warning.authority || "未提供"}</p>
          <p>源记录在该快照中未取消；当前有效性及生效、到期条款仍需核验。</p>
          <a href={warning.sourceUrl} target="_blank" rel="noreferrer">在 NGA 官方源核对 {warning.reference} ↗</a>
        </details>
      </article>)}
    </div>}
    <p className="topic-maritime-boundary">{evidence.limitations}</p>
    <details className="topic-maritime-rule"><summary>筛选与覆盖口径</summary><p>{evidence.selectionRule}</p></details>
  </section>;
}
