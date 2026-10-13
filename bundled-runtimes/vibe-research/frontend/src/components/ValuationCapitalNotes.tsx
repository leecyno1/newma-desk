import {useState} from 'react';
import type {capitalNoteReferences} from '@/lib/valuationInputs';
import type {CapitalEvidenceInput} from '@/lib/valuationReview';

export function ValuationCapitalNotes({references, disabled, input, onChange}: {
  references: ReturnType<typeof capitalNoteReferences>; disabled: boolean;
  input: CapitalEvidenceInput; onChange: (input: CapitalEvidenceInput) => void;
}) {
  const [quotes,setQuotes] = useState<Record<string,string>>({});
  const [status,setStatus] = useState('');
  if (!references.length) return null;
  return <section aria-label="已保存资本附注参考" className="space-y-2">
    <p className="text-muted-foreground">附注仅是证据，不代表金额已核验。展开后复制所需原文段（保留表头及限定条件），不会自动回填数值。</p>
    {references.map(({workbookId,savedAt,source})=>{
      const note=source.capitalNote!,key=`${workbookId}:${source.id}`,quote=quotes[key]||'';
      return <details key={key} className="border-l-2 border-border pl-3">
        <summary className="cursor-pointer">{source.label}{note.truncated?' · 内容已截断':''}</summary>
        <p className="my-2 text-xs text-muted-foreground">底稿 {workbookId} · 保存 {savedAt} · {note.topics.join(' / ')}</p>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-sm">{note.text}</pre>
        {source.url && /^https?:\/\//i.test(source.url) && <a className="text-primary underline" href={source.url} target="_blank" rel="noreferrer">核对 PDF 原页</a>}
        <textarea aria-label={`引用附注摘录 ${note.pdfPage} ${note.title}`} maxLength={2800} className="mt-2 min-h-20 w-full rounded border border-border bg-card p-2" placeholder="从上方复制连续原文，保留标题、表头和口径说明；计算写在下方计算说明中" value={quote} onChange={e=>setQuotes({...quotes,[key]:e.target.value})}/>
        <button className="rounded border border-border px-3 py-2 disabled:opacity-50" disabled={disabled||!quote.trim()} onClick={()=>{
          if(!note.text.includes(quote.trim())){setStatus('摘录必须是该附注中连续的原文，请勿改写或拼接。');return;}
          const citation=`财报底稿 ${workbookId} · 保存 ${savedAt} · ${note.title} · PDF 第 ${note.pdfPage} 页\n${quote.trim()}`;
          if(input.excerpt.includes(citation)){setStatus('该段已引用');return;}
          const excerpt=[input.excerpt,citation].filter(Boolean).join('\n\n');
          const locator=[input.locator,`PDF 第 ${note.pdfPage} 页`].filter(Boolean).join('；');
          if(excerpt.length>3000||locator.length>240){setStatus('原文或页码栏已达长度上限，请整理摘录后重试。');return;}
          onChange({...input,title:input.title||source.label,url:input.url||source.url||'',locator,excerpt});
          setStatus('已引用附注原文；金额与确认状态未自动补齐。');
        }}>引用此段附注</button>
      </details>;
    })}
    {status && <p role="status">{status}</p>}
  </section>;
}
