import type { Holding, Snapshot } from './PortfolioDiagnosis';
import { RiskTable } from './RiskAnalytics';

const holdingFields:Partial<Record<keyof Holding,string>>={assetType:'资产类型',market:'市场',symbol:'代码',name:'名称',account:'账户',currency:'币种',bookValue:'账面金额',fxToBase:'折算汇率',availableCash:'可用现金',equityBeta:'权益 Beta',equityBenchmark:'对冲基准',ratePnlPerBp:'整笔利率每基点损益',direction:'期货方向',notional:'名义金额',issuer:'发行人',source:'依据',modifiedDuration:'修正久期',contracts:'持仓手数',contractDv01:'每手 DV01',rateAsOf:'利率参数日期',expiryDate:'合约到期日',proceedsAmount:'预计到账金额',proceedsDate:'预计到账日',proceedsAccount:'收款账户',proceedsSource:'到账依据'};
const parameters:Partial<Record<keyof Snapshot,string>>={navWarningFloor:'净值预警线',productId:'产品归属编号',name:'组合名称',asOf:'持仓截止日',baseCurrency:'基准币种',navFloor:'净值底线',nearTermOutflow:'近期需留资金',cashNeedDate:'资金观察日'};
type Change={label:string;before:unknown;after:unknown};
const normalize=(value:unknown)=>value==null?'':value;
const identity=(p:Holding)=>JSON.stringify([p.account,p.assetType,p.market,p.symbol,p.direction||'']);
function fields<T extends object>(before:T,after:T,labels:Partial<Record<keyof T,string>>):Change[]{
  return (Object.keys(labels) as Array<keyof T>).filter(key=>normalize(before[key])!==normalize(after[key])).map(key=>({label:labels[key]!,before:before[key],after:after[key]}));
}

export function compareSnapshots(before:Snapshot,after:Snapshot){
  const old=new Map(before.holdings.map(p=>[identity(p),p]));
  const next=new Map(after.holdings.map(p=>[identity(p),p]));
  const scenarioText=(s:Snapshot)=>(s.additionalScenarios||[]).map(item=>`${item.label}：权益 ${display(item.equityShockPct)}%，利率 ${display(item.rateShockBp)}bp`).join('；')||'仅基础情景';
  const scenarioChanges=scenarioText(before)===scenarioText(after)?[]:[{label:'自定义压力情景',before:scenarioText(before),after:scenarioText(after)}];
  const allocationText=(s:Snapshot)=>(s.outflowAllocations||[]).map(a=>`${a.account}：${display(a.amount)} ${s.baseCurrency}`).sort().join('；')||'未分配到账户';
  const allocationChanges=allocationText(before)===allocationText(after)?[]:[{label:'账户预留分配',before:allocationText(before),after:allocationText(after)}];
  return {
    parameters:[...fields(before,after,parameters),...scenarioChanges,...allocationChanges],
    added:after.holdings.filter(p=>!old.has(identity(p))),
    removed:before.holdings.filter(p=>!next.has(identity(p))),
    changed:after.holdings.flatMap(p=>{const previous=old.get(identity(p));if(!previous)return [];const changes=fields(previous,p,holdingFields);return changes.length?[{holding:p,fields:changes}]:[]}),
  };
}
const display=(value:unknown)=>value==null||value===''?'未填写':String(value);
const title=(p:Holding)=>`${p.name} · ${p.market}:${p.symbol} · ${p.account} · ${p.currency}`;
function HoldingValues({holding}:{holding:Holding}){
  return <details><summary>查看完整输入</summary>{(Object.keys(holdingFields) as Array<keyof Holding>).filter(k=>normalize(holding[k])!=='').map(k=><p key={k}>{holdingFields[k]}：{display(holding[k])}</p>)}</details>;
}

export function SnapshotChanges({before,after,review=false}:{before:Snapshot;after:Snapshot;review?:boolean}){
  const diff=compareSnapshots(before,after);
  const count=diff.parameters.length+diff.added.length+diff.removed.length+diff.changed.length;
  const heading=review?'来源与复核输入变更':'保存前变更核对';
  return <section aria-label={heading} className="diagnosis-conclusion">
    <h3>{heading}</h3>
    <p>相对所选快照：新增 {diff.added.length} 行 · 移除 {diff.removed.length} 行 · 修改 {diff.changed.length} 行 · 组合参数 {diff.parameters.length} 项</p>
    {!count?<p>{review?'两份快照的原始输入没有变化；报告差异仍须核对研究证据及评估依据。':'原始输入没有变化。本次保存仍会重新评估；研究证据或计算口径变化可能生成新报告。'}</p>:<RiskTable label="快照输入变更" heads={['对象 / 操作','字段',review?'来源值':'原值',review?'复核值':'预览值']}>
      {diff.parameters.map(c=><tr key={c.label}><td>组合参数</td><td>{c.label}</td><td>{display(c.before)}</td><td>{display(c.after)}</td></tr>)}
      {diff.changed.flatMap((item,i)=>item.fields.map(c=><tr key={`${i}:${c.label}`}><td>修改 · {title(item.holding)}</td><td>{c.label}</td><td style={{whiteSpace:'pre-wrap'}}>{display(c.before)}</td><td style={{whiteSpace:'pre-wrap'}}>{display(c.after)}</td></tr>))}
      {diff.added.map((p,i)=><tr key={`add:${i}`}><td>新增 · {title(p)}</td><td>持仓行</td><td>—</td><td><HoldingValues holding={p}/></td></tr>)}
      {diff.removed.map((p,i)=><tr key={`remove:${i}`}><td>移除 · {title(p)}</td><td>持仓行</td><td><HoldingValues holding={p}/></td><td>—</td></tr>)}
    </RiskTable>}
    <p className="method-note">仅比较原始输入，不是成交或收益归因。账户、资产类型、市场、代码或方向改变时按移除＋新增列示；金额沿用各字段原有币种和单位，不跨币种相减。{review?'只读已保存版本，不生成成交或修改记录。':'修改后必须重新预览。'}</p>
  </section>;
}
