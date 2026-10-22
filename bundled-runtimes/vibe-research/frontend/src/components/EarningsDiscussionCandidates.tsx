import { ReportSourceLink } from '@/components/ReportSourceLink';
import {researchApiUrl, type EarningsPdfImport} from '@/lib/api';

export function EarningsDiscussionCandidates({document, selected, disabled, onChange}: {
  document: EarningsPdfImport; selected: string[]; disabled: boolean; onChange: (ids: string[])=>void;
}) {
  if (!document.discussion?.length) return null;
  return <section aria-label="经营讨论候选" className="space-y-2 border-t border-border pt-3 text-sm">
    <h3 className="font-semibold">经营讨论原文 · 已选 {selected.length} / {document.discussion.length} 页</h3>
    <p className="text-muted-foreground">主题是检索线索，不是风险结论。请展开核对；仅勾选原文随底稿保存并交给 Agent，表格不自动转为指标。</p>
    {document.discussion.map(passage=><div key={passage.id} className="flex items-start gap-2">
      <input type="checkbox" className="mt-1" aria-label={`采用经营讨论第 ${passage.page} 页`} disabled={disabled} checked={selected.includes(passage.id)} onChange={e=>onChange(e.target.checked?[...selected,passage.id]:selected.filter(id=>id!==passage.id))}/>
      <details className="min-w-0 flex-1"><summary className="cursor-pointer">{passage.topics.join(' / ')} · 第 {passage.page} 页{passage.truncated?' · 内容已截断':''}</summary>
        <ReportSourceLink className="text-primary underline" href={`${researchApiUrl(`/myreports/file/${document.reportId}?inline=true`)}#page=${passage.page}`} target="_blank" rel="noreferrer">核对 PDF 原页</ReportSourceLink>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap py-2 text-sm">{passage.text}</pre>
      </details>
    </div>)}
  </section>;
}
