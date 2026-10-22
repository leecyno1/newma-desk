import {useEffect,useRef,useState} from 'react';
import type {useCompanyEvidence} from './useCompanyEvidence';

export function CompanyLinksPanel({company}:{company:ReturnType<typeof useCompanyEvidence>}) {
  const {links,savedLinks} = company;
  const [message,setMessage] = useState('');
  const [removing,setRemoving] = useState('');
  const draftKey=JSON.stringify([company.selectedId,company.reason]);
  const activeDraft=useRef(draftKey);activeDraft.current=draftKey;
  useEffect(()=>{setMessage('');setRemoving('');},[company.selectedId,company.reason]);
  const ready = links.status==='ready' && !links.busy;
  async function save() {
    setMessage('');
    try {if (await company.saveAssociation() && activeDraft.current===draftKey) setMessage('关联依据已保存到当前工作区；重载后仍须重新核验。');}
    catch (error) {if(activeDraft.current===draftKey)setMessage(error instanceof Error?error.message:'保存失败');}
  }
  return <section className="company-links" aria-label="已保存公司关联">
    <div className="section-title"><h3>业务关联备忘 · 当前行业</h3><button disabled={!links.available||links.busy} onClick={()=>{
      setRemoving('');setMessage('');void company.reloadLinks();
    }}>{links.busy?'关联处理中…':'读取 / 刷新已存关联'}</button></div>
    <p>保存关联依据及最近核验版本，不复制财报；更新将替换此公司在当前行业的上一份备忘，非完整复核日志。</p>
    {links.error&&<p role="alert" className="error">{links.error}</p>}
    {ready&&<p role="status">当前行业 {savedLinks.length} 条已存关联 · 工作区共 {links.book.entries.length} / 50 条</p>}
    {!links.available&&<p>需在 Desk 工作区读写，不使用浏览器共享缓存。</p>}
    {links.status==='idle'&&<p>请先读取关联库，再保存当前已核验的业务关联。</p>}
    {!links.writable && <p>当前会话没有公司关联写入权限。</p>}
    <button disabled={!links.writable||!ready||!company.evidence||!company.confirmed||company.data?.workbooks.find(row=>row.id===company.selectedId)?.mode!=='reported'} onClick={()=>void save()}>确认保存 / 更新当前关联</button>
    {message&&<p role="status">{message}</p>}
    <div className="company-link-list">{savedLinks.map(link=><article key={link.workbookId}>
      <h4>{link.security.name} · {link.security.symbol} · {link.fiscalPeriod.periodEnd||'期间未确认'}</h4>
      <p>{link.reason}</p><p className="caution">{link.state}</p>
      <p>上次核验 {new Date(link.reviewedAt).toLocaleString('zh-CN',{hour12:false})} · 财报版本 {link.sourceRevision} · 行业截至 {link.report.periodEnd}</p>
      <button disabled={!ready||company.status!=='ready'||!company.data?.workbooks.some(row=>row.id===link.workbookId)} onClick={()=>{
        company.restore(link);setMessage('已载入关联依据；请核对当前底稿并点击“确认业务关联并核验”。');setRemoving('');
      }}>载入待核验</button>
      {removing===link.workbookId?<><p>仅移除这条关联备忘，不删除财报或其他研究记录。</p>
        <button disabled={!ready||!links.writable} onClick={()=>void (async()=>{
          setMessage('');
          if (await links.save({...links.book,entries:links.book.entries.filter(row=>row.industry!==link.industry||row.workbookId!==link.workbookId)})) {
            setRemoving('');setMessage('已移除关联备忘，财报及其他研究记录未改动。');
          }
        })()}>确认移除关联</button><button disabled={!ready} onClick={()=>setRemoving('')}>保留关联</button>
      </>:<button disabled={!ready||!links.writable} onClick={()=>{setRemoving(link.workbookId);setMessage('');}}>移除关联</button>}
    </article>)}</div>
  </section>;
}
