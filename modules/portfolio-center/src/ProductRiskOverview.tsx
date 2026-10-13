import { useEffect, useState } from 'react';
import type { PortfolioIdentity } from './api';
import { callPortfolioImport as call } from './api';
import type { ImportDiagnosis } from './PortfolioDiagnosis';
import { RiskTable } from './RiskAnalytics';
import { thresholdLabels } from './NavThresholds';

const amount=(value:number|null)=>value==null?'未评估':value.toLocaleString('zh-CN',{maximumFractionDigits:2});
export function productRiskSummary(data:ImportDiagnosis){
  const r=data.report;
  const balances=r.scenarios.flatMap(s=>s.cashByAccount.map(c=>({...c,scenario:s.label})));
  const known=balances.filter(c=>c.remaining!=null).sort((a,b)=>a.remaining!-b.remaining!);
  const floors=[r.navHeadroom,...r.scenarios.map(s=>s.floorHeadroom)];
  const knownFloors=floors.filter((v):v is number=>v!=null);
  const productCash=r.scenarios.map(s=>s.cashAfterKnownNeeds);
  const knownProductCash=productCash.filter((v):v is number=>v!=null);
  return {
    account:known[0]?.account,
    cashScenario:known[0]?.scenario,
    cash:known[0]?.remaining??null,
    cashComplete:balances.length>0&&balances.every(c=>c.remaining!=null),
    floor:knownFloors.length?Math.min(...knownFloors):null,
    floorComplete:floors.length>1&&floors.every(v=>v!=null),
    productCash:knownProductCash.length?Math.min(...knownProductCash):null,
    productCashComplete:productCash.length>0&&productCash.every(v=>v!=null),
  };
}

export function productReviewFlags(data:ImportDiagnosis,now=Date.now()){
  const r=data.report,risk=productRiskSummary(data);
  const triggered=(status:string)=>['floor_breached','floor_reached','warning'].includes(status);
  return {
    current:(r.navHeadroom!=null&&r.navHeadroom<=0)||Boolean(r.navThresholds?.rows[0]&&triggered(r.navThresholds.rows[0].status)),
    scenario:r.scenarios.some(s=>s.floorHeadroom!=null&&s.floorHeadroom<=0)||Boolean(r.navThresholds?.rows.slice(1).some(s=>triggered(s.status))),
    cash:(risk.cash!=null&&risk.cash<0)||(risk.productCash!=null&&risk.productCash<0),
    incomplete:r.nav==null||r.gaps.length>0||!risk.floorComplete||!risk.cashComplete||!risk.productCashComplete||r.coverage.valued<r.coverage.total||r.coverage.sensitivity<r.coverage.total,
    stale:now-Date.parse(`${data.snapshot.asOf}T00:00:00`)>4*86400000,
  };
}
const filters={all:'全部产品',current:'快照已触线',scenario:'压力情景触线',cash:'情景现金缺口',incomplete:'资料 / 测算不完整',stale:'持仓日超过 4 天'};

export function ProductRiskOverview({identity,revision,selectedId,disabled,onSelect}:{identity:PortfolioIdentity;revision?:string;selectedId?:string;disabled:boolean;onSelect(value:ImportDiagnosis):void}){
  const [items,setItems]=useState<ImportDiagnosis[]>([]);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const [filter,setFilter]=useState<keyof typeof filters>('all');
  useEffect(()=>{
    let active=true;setLoading(true);setError('');
    void call<ImportDiagnosis[]>(identity,'import-products').then(data=>{if(active)setItems(data)})
      .catch(e=>{if(active){setItems([]);setError(e instanceof Error?e.message:String(e))}})
      .finally(()=>{if(active)setLoading(false)});
    return()=>{active=false};
  },[identity.userId,identity.workspaceId,revision]);
  const tagged=items.map(item=>({item,flags:productReviewFlags(item)}));
  const visible=tagged.filter(({flags})=>filter==='all'||flags[filter]);
  return <details className="diagnosis-help product-risk-overview" open><summary>产品风险总表 · {loading?'读取中':`${items.length} 个已归属产品`}</summary>
    <p className="method-note">每产品取持仓截止日最新、同日最后保存的一份快照；不是实时监控。金额各用该产品基准币，不跨产品抵销。未填写产品编号的快照不进入本表，产品清单及账户完整性仍需人工核验。</p>
    {error&&<p role="alert">产品总表读取失败：{error}</p>}
    {!loading&&!error&&!items.length&&<p>尚无已归属产品。导入时填写固定产品编号；旧快照请编辑、确认归属后另存。</p>}
    {!!items.length&&<><label>产品核验筛选<select aria-label="产品核验筛选" value={filter} onChange={e=>setFilter(e.target.value as keyof typeof filters)}>{(Object.keys(filters) as Array<keyof typeof filters>).map(key=><option key={key} value={key}>{filters[key]} · {key==='all'?items.length:tagged.filter(t=>t.flags[key]).length}</option>)}</select></label><p className="method-note">筛选项可重叠，不改变当前评估对象。超过 4 天按自然日提示，不是交易日规则；处置结案不移除报告中的提示。</p></>}
    {!!items.length&&!visible.length&&<p role="status">没有符合该筛选的产品，不代表其他风险已排除。</p>}
    {!!visible.length&&<RiskTable label="产品风险总表" heads={['产品 / 账户','持仓日 / 币种','账面净资产','快照 / 情景最小底线余量','情景最差账户现金余量','提示 / 操作']}>
      {visible.map(({item,flags})=>{
        const r=item.report;const risk=productRiskSummary(item);
        const old=flags.stale;
        const accounts=[...new Set(item.snapshot.holdings.map(h=>h.account))];
        return <tr key={item.snapshot.productId}>
          <td><strong>{item.snapshot.name}</strong><small>{item.snapshot.productId}</small><details><summary>{accounts.length} 个账户 · {item.snapshot.holdings.length} 笔持仓</summary>{accounts.map(a=><p key={a}>{a} · {item.snapshot.holdings.filter(h=>h.account===a).length} 笔</p>)}</details></td>
          <td>{item.snapshot.asOf}<small>{r.baseCurrency} · {old?'过期，仅历史参考':'导入估值，未对账'}</small></td>
          <td>{amount(r.nav)}{r.navThresholds&&<><small>快照：{thresholdLabels[r.navThresholds.rows[0]?.status]||'未评估'}</small><small>情景触线 {r.navThresholds.rows.slice(1).filter(row=>['floor_breached','floor_reached','warning'].includes(row.status)).length} 项 · 待评估 {r.navThresholds.rows.slice(1).filter(row=>row.status==='unassessed').length} 项</small></>}</td>
          <td className={risk.floor!=null&&risk.floor<0?'risk-shortfall':''}>{amount(risk.floor)}{risk.floor!=null&&risk.floor<0&&<small>底线缺口</small>}{!risk.floorComplete&&<small>底线或情景未评估完整</small>}</td>
          <td className={risk.cash!=null&&risk.cash<0?'risk-shortfall':''}>{amount(risk.cash)}{risk.cash!=null&&risk.cash<0&&<small>情景账户现金缺口</small>}<small>{risk.account||'无已知账户余额'}{!risk.cashComplete?' · 尚有未评估项':''}</small><small>对应情景：{risk.cashScenario||'未提供'}</small><small className={risk.productCash!=null&&risk.productCash<0?'risk-shortfall':''}>产品扣全部预留：{amount(risk.productCash)}{!risk.productCashComplete?' · 未评估完整':''}</small></td>
          <td>{r.alerts.length} 项提示 · {r.gaps.length} 项待核验<br/><button className="secondary-button" disabled={disabled||selectedId===item.id} onClick={()=>onSelect(item)} aria-label={`查看产品 ${item.snapshot.productId}`}>{selectedId===item.id?'正在查看':'查看产品'}</button></td>
        </tr>;
      })}
    </RiskTable>}
    {!!items.length&&<p className="method-note">底线余量取快照及各情景最小值；现金取各账户各情景最小已知余额，不相加。现金已扣账户预留，但产品层尚未分配的预留须在产品详情继续核验。没有触发提示不等于安全。</p>}
  </details>;
}
