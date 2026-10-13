import { RiskTable } from './RiskAnalytics';

type Member = {name:string;symbol:string;market:string;account:string;assetType:string;baseValue:number|null;source:string};
export type IssuerExposureData = {
  items:Array<{issuer:string;knownBaseValue:number;baseValue:number|null;stockValue:number|null;bondValue:number|null;navWeightPct:number|null;securityCount:number;accounts:string[];crossAsset:boolean;members:Member[]}>;
  unmatched:Array<{name:string;symbol:string;market:string;account:string;baseValue:number|null;reason:string}>;
  coverage:{directRows:number;identifiedRows:number;valuedRows:number;identifiedValuePct:number|null;unmatchedKnownValue:number;excludedFundRows:number;excludedFundKnownValue:number};
  basis:string;
};
const fmt=(n:number|null)=>n==null?'未评估':n.toLocaleString('zh-CN',{maximumFractionDigits:2});

export function IssuerExposure({data,currency}:{data:IssuerExposureData;currency:string}) {
  const c=data.coverage;
  return <section aria-label="发行人集中暴露">
    <h3>发行人集中暴露 · 直接持有</h3>
    <p className="method-note">股票 / 债券已归属 {c.identifiedRows} / {c.directRows} 行；金额覆盖 {c.identifiedValuePct==null?'未评估':`${fmt(c.identifiedValuePct)}%`}（分母为直接股票和债券总市值）。以下金额均为 {currency}。</p>
    {data.items.length>0?<RiskTable label="发行人集中暴露明细" heads={['发行人 / 跨账户','股票市值','债券市值','合计已识别敞口','已识别市值 / NAV','持仓依据']}>
      {data.items.map(item=><tr key={item.issuer}><td><strong>{item.issuer}</strong><small>{item.securityCount} 只证券 · {item.accounts.join('、')}{item.crossAsset?' · 股债同主体':''}</small></td><td>{fmt(item.stockValue)}</td><td>{fmt(item.bondValue)}</td><td>{item.baseValue==null?`已知 ${fmt(item.knownBaseValue)} · 未完整`:fmt(item.baseValue)}</td><td>{item.navWeightPct==null?'未评估':`${fmt(item.navWeightPct)}%`}</td><td><details><summary>展开来源 {item.members.length} 行</summary>{item.members.map((m,i)=><p key={i}>{m.name} · {m.market}:{m.symbol} · {m.account}<small>{fmt(m.baseValue)} {currency} · {m.source}</small></p>)}</details></td></tr>)}
    </RiskTable>:<p>暂无可明确归属的股票或债券，不能据此判断发行人风险分散。</p>}
    {data.unmatched.length>0&&<details className="diagnosis-help"><summary>发行人待核对 {data.unmatched.length} 行 · 已知未归属金额 {fmt(c.unmatchedKnownValue)} {currency}</summary><RiskTable label="发行人归属缺口" heads={['证券 / 账户','已知市值','待核对原因']}>{data.unmatched.map((m,i)=><tr key={i}><td>{m.name}<small>{m.market}:{m.symbol} · {m.account}</small></td><td>{fmt(m.baseValue)}</td><td>{m.reason}</td></tr>)}</RiskTable></details>}
    {c.excludedFundRows>0&&<p className="method-note">另有 {c.excludedFundRows} 行基金尚未穿透，已知市值 {fmt(c.excludedFundKnownValue)} {currency}。基金管理人不是底层资产发行人；这些基金可能进一步增加对上述主体的暴露。</p>}
    <p className="method-note">{data.basis} NAV 非正或估值不完整时不计算 NAV 占比。这里不是违约概率、回收率或信用评级。</p>
  </section>;
}
