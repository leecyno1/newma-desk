import { BASES } from "./company";
import { fmt } from "./research";
import type { useCompanyEvidence } from "./useCompanyEvidence";
import {CompanyLinksPanel} from './CompanyLinksPanel';
import {RevenueComparisonPanel} from './RevenueComparisonPanel';
import {chainHandoffUrl} from './chainHandoff';

export function CompanyPanel({company, href, chainHref}: {company: ReturnType<typeof useCompanyEvidence>; href?: string; chainHref?: string}) {
  const evidence = company.evidence;
  return <section className="production-panel company-panel" aria-label="行业到公司核验">
    <div className="section-title"><div><small>INDUSTRY → COMPANY</small><h2>行业到公司 · 财报核验</h2></div>
      <button onClick={company.load} disabled={!company.available || company.status === "loading"}>{company.status === "loading" ? "读取已保存底稿…" : "读取 / 刷新财报底稿"}</button></div>
    <p>只读工作区财报；先确认业务关联，不改原件。财报变更在刷新时比对，不自动监听其他页面。</p>
    {href && <a href={href} target="_blank" rel="noreferrer">打开财报研究 ↗</a>}
    {!company.available && <p>须在 Desk 读取底稿，独立页无工作区身份。</p>}
    {company.error && <p role="alert" className="error">{company.error}。旧公司证据已撤下。</p>}
    {company.status === "ready" && !company.data?.workbooks.length && <p role="status">工作区暂无财报底稿，请先保存并同步。</p>}
    {!!company.data?.workbooks.length && <div className="company-controls">
      <label>选择财报底稿<select aria-label="选择公司财报底稿" value={company.selectedId} onChange={e => company.select(e.target.value)}><option value="">请选择，不自动关联</option>
        {company.data.workbooks.map(row => <option key={row.id} value={row.id}>{row.security?.name} · {row.security?.symbol} · {row.fiscalPeriod?.periodEnd || "期间未确认"} · {BASES[row.fiscalPeriod?.basis ?? ""] ?? "口径未确认"}</option>)}</select></label>
      {company.selectedId && <><label>业务关联依据<textarea aria-label="业务关联依据" rows={2} maxLength={800} value={company.reason} onChange={e => company.editReason(e.target.value)} placeholder="说明相关业务及年报出处。"/></label>
        <button disabled={!company.reason.trim() || company.confirmed} onClick={company.confirm}>{company.confirmed ? "已确认研究关联" : "确认业务关联并核验"}</button>
        <p>人工关联≠官方分类。</p></>}
    </div>}
    <CompanyLinksPanel key={`${company.links.scope}|${company.viewKey}`} company={company}/>
    {evidence && <><h3>{evidence.security.name} · {evidence.security.symbol} · {evidence.security.currency}</h3>
      <p>行业截至 {evidence.industryPeriodEnd} / 公司截至 {evidence.companyPeriodEnd ?? "未确认"} · 底稿保存 {evidence.savedAt} · 版本 {evidence.sourceRevision}</p>
      <p className="caution">{evidence.timingNote}</p>
      <div className="company-metrics">{evidence.rows.map(row => <article key={row.id}><h3>{row.label}</h3>
        <strong>{fmt(row.value, row.value == null ? "" : ` ${row.unit}`, 2)}</strong><p>{row.state} · {row.basis}</p>
        {row.issues.length > 0 && <p>{row.issues.join("；")}</p>}
        {row.sources.map(source => <p key={source.id}>{source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.label} ↗</a> : source.label}{source.pdfPage ? ` · PDF第 ${source.pdfPage} 页` : ""}</p>)}
      </article>)}</div>
      {!!evidence.revenueGroups.length&&<section aria-label="公司主营收入结构">
        <h3>主营收入结构 · 按原表维度分开</h3><p>用于核对业务关联，不自动映射行业；组内占比≠公司总收入占比。</p>
        <div className="company-revenue">{evidence.revenueGroups.map(item=><article key={item.sourceId}>
          <h3>{item.group?.title??item.label}</h3>{item.issue&&<p className="caution">{item.issue}</p>}
          {item.group&&item.summary&&<>
            <p>{item.periodEnd} · 年度主营业务 · {item.group.currency} · PDF 第 {item.group.pdfPage} 页</p>
            <p>{item.summary.denominatorLabel}：{fmt(item.summary.denominator,' 亿元',4)}</p>
            {item.summary.reason&&<p className="caution">{item.summary.reason}</p>}
            {item.group.skippedRows>0&&<p className="caution">有 {item.group.skippedRows} 行未可靠识别，请核对原页。</p>}
            <table><thead><tr><th>项目</th><th>收入 / 亿元</th><th>组内占比</th></tr></thead><tbody>{item.summary.rows.map(row=><tr key={row.label}>
              <td>{row.label}</td><td>{fmt(row.value,'',4)}</td><td>{fmt(row.sharePct,'%',2)}{row.sharePct!==null&&<span className="revenue-share" style={{width:`${row.sharePct}%`}}/>}</td>
            </tr>)}</tbody></table>
            <details><summary>核对原文与单位</summary><pre>{item.group.columnHeader}{'\n'}{[...item.group.rows,...(item.group.total?[item.group.total]:[])].map(row=>`${row.label}：${row.rawValue} ${row.rawUnit}\n${row.excerpt}`).join('\n')}</pre></details>
          </>}
          {item.url&&<a href={item.url} target="_blank" rel="noreferrer">{item.label} ↗</a>}
          {chainHref&&chainHandoffUrl(chainHref,evidence,item.sourceId,company.identity)&&<p><a
            href={chainHandoffUrl(chainHref,evidence,item.sourceId,company.identity)!} target="_blank" rel="noreferrer">带此表进入产业链核对 ↗</a>
            <small>仅传底稿标识；目标页重新读取，不自动建立供需关系。</small></p>}
        </article>)}</div>
      </section>}
      <RevenueComparisonPanel company={company}/>
      <h3>证据局限</h3><ul>{evidence.gaps.map(gap => <li key={gap}>{gap}</li>)}</ul>
    </>}
  </section>;
}
