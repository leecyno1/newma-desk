import {summarizeBusinessRevenue} from '@newma-desk/contracts/business-revenue';
import {companyRevenueGroups,type CompanyWorkbook} from './company';

export function sameCompany(a:CompanyWorkbook,b:CompanyWorkbook) {
  return !!a.security.symbol && a.security.symbol===b.security.symbol && a.security.market===b.security.market && a.security.currency===b.security.currency;
}
export function compareRevenue(current:CompanyWorkbook,prior:CompanyWorkbook,currentId:string,priorId:string,confirmed:boolean) {
  if(!confirmed)return null;
  const now=companyRevenueGroups(current).find(row=>row.sourceId===currentId);
  const before=companyRevenueGroups(prior).find(row=>row.sourceId===priorId);
  const a=now?.group,b=before?.group;
  const end=current.fiscalPeriod.periodEnd??'',start=prior.fiscalPeriod.periodEnd??'';
  const validDate=(value:string)=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
  if(!sameCompany(current,prior)||current.id===prior.id||!validDate(start)||!validDate(end)||start>=end
    ||!a||!b||a.dimension!==b.dimension||a.scope!==b.scope||a.currency!==b.currency||a.unit!==b.unit)return null;
  const annual=Number(end.slice(0,4))-Number(start.slice(0,4))===1&&end.slice(4)===start.slice(4);
  const nowSummary=summarizeBusinessRevenue(a),priorSummary=summarizeBusinessRevenue(b);
  const labels=[...new Set([...a.rows.map(row=>row.label),...b.rows.map(row=>row.label)])];
  const sameRows=a.rows.length===b.rows.length&&labels.length===a.rows.length;
  const shareReason=!sameRows?'项目集合变化，不比较结构占比'
    :a.skippedRows||b.skippedRows?'存在未识别行，不比较结构占比'
    :!!a.total!==!!b.total?'两期分母类型不同，不比较结构占比'
    :nowSummary.reason||priorSummary.reason;
  const rows=labels.map(label=>{
    const x=nowSummary.rows.find(row=>row.label===label),y=priorSummary.rows.find(row=>row.label===label);
    const status=!x?'仅对照期列示（不等于退出业务）':!y?'仅本期列示（不等于新增业务）':'同名项目，口径经人工确认';
    const reason=!x||!y?'缺少同名对照，不补零':y.value<=0?'对照期非正数，不计算增长率':x.value<0?'本期为负数，不计算普通增长率':null;
    return {label,current:x?.value??null,prior:y?.value??null,delta:x&&y?x.value-y.value:null,
      changePct:reason||!x||!y?null:(x.value-y.value)/y.value*100,
      shareChangePp:!shareReason&&x?.sharePct!=null&&y?.sharePct!=null?x.sharePct-y.sharePct:null,status,reason};
  });
  return {security:current.security,dimension:a.dimension,periodEnd:end,priorPeriodEnd:start,
    changeLabel:annual?'同比变化':'跨期变化（非同比）',shareReason,rows,
    current:{workbookId:current.id,savedAt:current.updatedAt,sourceId:currentId,url:now!.url,page:a.pdfPage,skippedRows:a.skippedRows,denominator:nowSummary.denominator,denominatorLabel:nowSummary.denominatorLabel},
    prior:{workbookId:prior.id,savedAt:prior.updatedAt,sourceId:priorId,url:before!.url,page:b.pdfPage,skippedRows:b.skippedRows,denominator:priorSummary.denominator,denominatorLabel:priorSummary.denominatorLabel},
    boundary:'人工确认两期业务口径可比；仅精确同名匹配，不自动映射更名，不是有机增长、公司总收入贡献或行业因果归因。仅本次会话，刷新或切换需重新确认。'};
}
