import type {useCompanyEvidence} from './useCompanyEvidence';
import {fmt} from './research';

export function RevenueComparisonPanel({company}:{company:ReturnType<typeof useCompanyEvidence>}) {
  const {comparisonBooks,comparisonChoice:choice,priorGroups,comparison}=company;
  const groups=company.evidence?.revenueGroups.filter(row=>row.group)??[];
  const currentGroup=groups.find(row=>row.sourceId===choice.currentSourceId);
  const candidates=priorGroups.filter(row=>row.group&&row.group.dimension===currentGroup?.group?.dimension);
  const ready=!!currentGroup&&candidates.some(row=>row.sourceId===choice.priorSourceId);
  return <section className="company-links" aria-label="主营收入跨期比较">
    <h3>主营收入跨期比较</h3><p>只比较同一公司已采纳的年度主营表。先核对重述、业务边界与名称口径；同名不保证可比，更名不自动匹配。</p>
    {!comparisonBooks.length&&<p>暂无同公司较早年度底稿，请在财报研究导入、采纳收入结构并保存后刷新。</p>}
    {!!comparisonBooks.length&&<div className="company-controls revenue-comparison-controls">
      <label>对照年度底稿<select aria-label="对照年度底稿" value={choice.priorId} onChange={e=>company.chooseComparison('priorId',e.target.value)}>
        <option value="">请选择对照底稿</option>{comparisonBooks.map(book=><option key={book.id} value={book.id}>{book.security.name} · {book.fiscalPeriod.periodEnd} · {book.fiscalPeriod.label}</option>)}
      </select></label>
      <label>本期收入表<select aria-label="本期收入表" value={choice.currentSourceId} onChange={e=>company.chooseComparison('currentSourceId',e.target.value)}>
        <option value="">请选择本期表</option>{groups.map(row=><option key={row.sourceId} value={row.sourceId}>{row.group!.title} · 第 {row.group!.pdfPage} 页</option>)}
      </select></label>
      <label>对照期收入表<select aria-label="对照期收入表" value={choice.priorSourceId} onChange={e=>company.chooseComparison('priorSourceId',e.target.value)} disabled={!choice.priorId||!currentGroup}>
        <option value="">请选择同分类表</option>{candidates.map(row=><option key={row.sourceId} value={row.sourceId}>{row.group!.title} · 第 {row.group!.pdfPage} 页</option>)}
      </select></label>
      {choice.priorId&&currentGroup&&!candidates.length&&<p>对照底稿未提供同分类、同口径的已采纳收入表；不补零。</p>}
      <label className="revenue-comparison-check"><input type="checkbox" checked={!!choice.confirmedAt} disabled={!ready} onChange={e=>company.confirmComparison(e.target.checked)}/>已核对两期原文、重述及业务分类口径，可作同名项目比较</label>
      <div className="revenue-comparison-sources">{[currentGroup,candidates.find(row=>row.sourceId===choice.priorSourceId)].map((row,index)=>row?.url?<p key={index}><a href={row.url} target="_blank" rel="noreferrer">核对{index?'对照期':'本期'}原文 · PDF 第 {row.group!.pdfPage} 页 ↗</a></p>:null)}</div>
    </div>}
    {!!choice.confirmedAt&&!comparison&&<p role="alert">所选表的身份、分类或期间未满足比较条件，请重新核对。</p>}
    {comparison&&<>
      <p>{comparison.priorPeriodEnd} → {comparison.periodEnd} · {comparison.changeLabel} · 收入金额单位：亿元</p>
      <p>本期分母：{comparison.current.denominatorLabel} {fmt(comparison.current.denominator,' 亿元',4)}；对照期分母：{comparison.prior.denominatorLabel} {fmt(comparison.prior.denominator,' 亿元',4)}。</p>
      {comparison.shareReason&&<p className="caution">{comparison.shareReason}。</p>}
      <div className="revenue-comparison-scroll" tabIndex={0} role="region" aria-label="收入跨期明细，可横向滚动"><table>
        <thead><tr><th>原表项目</th><th>对照期</th><th>本期</th><th>金额变化</th><th>{comparison.changeLabel} %</th><th>占比变化 pp</th><th>核验说明</th></tr></thead>
        <tbody>{comparison.rows.map(row=><tr key={row.label}><th scope="row">{row.label}</th><td>{fmt(row.prior,'',4)}</td><td>{fmt(row.current,'',4)}</td><td>{fmt(row.delta,'',4)}</td><td>{fmt(row.changePct,'%',2)}</td><td>{fmt(row.shareChangePp,'',2)}</td><td>{row.status}{row.reason?`；${row.reason}`:''}</td></tr>)}</tbody>
      </table></div><p className="muted">窄屏可横向滚动查看；“—”表示不可计算，不代表零。</p><p>{comparison.boundary}</p>
    </>}
  </section>;
}
