import { useState } from 'react';
import type { ImportDiagnosis } from './PortfolioDiagnosis';
import { RiskTable } from './RiskAnalytics';
export type Contribution={rowIndex:number;pnl:number|null;futuresLossDemand:number|null};
const amount=(n:number|null)=>n==null?'未评估':n.toLocaleString('zh-CN',{maximumFractionDigits:2});

export function ScenarioContributions({report}:{report:ImportDiagnosis['report']}){
  const [label,setLabel]=useState('');
  const scenario=report.scenarios.find(s=>s.label===label)||report.scenarios[0];
  if(!scenario?.contributions)return null;
  const entries=[...scenario.contributions].sort((a,b)=>{
    if(a.pnl===null)return b.pnl===null?0:-1;
    if(b.pnl===null)return 1;
    return a.pnl-b.pnl;
  });
  return <details className="diagnosis-help"><summary>逐笔持仓情景贡献 · 定位亏损与期货现金需求</summary>
    <label>贡献分析情景<select aria-label="贡献分析情景" value={scenario.label} onChange={e=>setLabel(e.target.value)}>{report.scenarios.map(s=><option key={s.label}>{s.label}</option>)}</select></label>
    <p>权益 {scenario.equityShockPct}% · 利率 {scenario.rateShockBp}bp · 组合损益 {amount(scenario.totalPnl)} {report.baseCurrency}</p>
    <RiskTable label="逐笔情景损益贡献" heads={['持仓 / 账户','情景损益（基准币）','期货亏损现金需求（基准币）','输入依据']}>
      {entries.map(c=>{const row=report.rows[c.rowIndex];return <tr key={c.rowIndex}><td>{row.name}<small>{row.market}:{row.symbol} · {row.account}</small></td><td className={c.pnl!=null&&c.pnl<0?'negative':''}>{amount(c.pnl)}</td><td>{row.assetType.endsWith('future')?amount(c.futuresLossDemand):'不适用'}</td><td><details><summary>{c.pnl===null?'缺参数，查看缺口':'查看参数与来源'}</summary><p>{row.source}</p><p>账面金额 {amount(row.bookValue)} {row.currency}</p>{['stock','fund'].includes(row.assetType)&&<p>权益 Beta {amount(row.equityBeta)} · 基准 {row.equityBenchmark||'未填写'}</p>}{row.assetType==='equity_future'&&<p>名义金额 {amount(row.notional)} {row.currency} · {row.direction==='short'?'空头':'多头'}</p>}{row.rateInputBasis&&<p>采用利率损益 {amount(row.ratePnlPerBpBase??null)} {report.baseCurrency}/bp</p>}<p>{row.gaps.join('；')||'输入字段齐备，未经独立核验'}</p>{row.rateInputBasis&&<p>{row.rateInputBasis}</p>}</details></td></tr>})}
    </RiskTable>
    <p className="method-note">金额均折算为 {report.baseCurrency}。先列未评估项，再按损益从低到高排序。仅拆解本情景的一阶损益，不是实际收益或统计风险贡献；现金需求是同一笔期货损失的另一个视角，不能与损益重复相加。现货账面盈利不视为可用现金，期货盈利也不自动抵销其他合约的现金需求。零仅表示该情景下的已建模损益为零。</p>
  </details>;
}
