import type { ReactNode } from 'react';
import type { Market, PortfolioDashboard, PortfolioPerformanceResult } from './types';
import { capitalExposure, concentrationDetail, historyDiagnostics, quoteStatus, RISK_LABELS, scenarioImpact, STRESS_SCENARIOS } from './risk';

const n=(value:number|null|undefined,digits=2)=>value==null?'—':value.toLocaleString('zh-CN',{maximumFractionDigits:digits});
const pct=(value:number|null|undefined)=>value==null?'—':`${n(value)}%`;
export function RiskTable({heads,children,label}:{heads:string[];children:ReactNode;label:string}) {
  return <div className="risk-table-scroll"><table className="risk-data-table" aria-label={label}><thead><tr>{heads.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;
}

export function ConcentrationAnalysis({dashboard,now}:{dashboard:PortfolioDashboard;now:number}) {
  const groups=concentrationDetail(dashboard,now);
  return <section className="folio-panel"><p className="method-note">按币种、证券合并跨账户持仓。余量=单一证券限额−当前权重；负值表示超限。超额敞口按当前持仓总市值固定测算，不等于建议卖出金额。</p>
    {groups.map(g=><div key={g.currency} className="risk-analysis-section"><div className="risk-section-heading"><strong>{g.currency} · {g.status==='passed'?'行情可用':RISK_LABELS[g.status]}</strong><span>持仓市值 {g.status==='passed'?n(g.total):'—'} · HHI {g.status==='passed'?n(g.hhi,4):'—'} · 有效证券 {g.status==='passed'?n(g.effective):'—'}</span></div>
      <RiskTable label={`${g.currency} 证券集中度`} heads={['证券 / 账户','市值','权重','累计权重','限额余量 / 百分点','超额敞口','集中度贡献']}>
        {g.rows.map(row=><tr key={`${row.market}:${row.symbol}`}><td><strong>{row.name}</strong><small>{row.market}:{row.symbol} · {row.accounts.join(' / ')}</small></td><td>{g.status==='passed'?n(row.value):'—'}</td><td>{g.status==='passed'?pct(row.weight):'—'}</td><td>{pct(row.cumulativeWeight)}</td><td className={row.headroomPct!=null&&row.headroomPct<0?'negative':''}>{n(row.headroomPct)}</td><td>{n(row.excessValue)}</td><td><div className="risk-cell-bar"><i style={{width:`${row.concentrationContributionPct||0}%`}}/></div>{pct(row.concentrationContributionPct)}</td></tr>)}
      </RiskTable></div>)}
    {!groups.length&&<p>尚无持仓，不能计算集中度。</p>}<p className="method-note">集中度贡献=w² / Σw²，只衡量持仓集中程度，不是波动风险贡献。行业、集团关联和因子集中度需要相应分类、持仓穿透和收益序列，当前不伪造这些结果。</p>
  </section>;
}

export function ExposureAnalysis({dashboard,now}:{dashboard:PortfolioDashboard;now:number}) {
  const capital=capitalExposure(dashboard,now);
  const groups=concentrationDetail(dashboard,now);
  const accountRows=dashboard.accounts.flatMap(account=>[...new Set([...dashboard.positions.filter(p=>p.accountId===account.id).map(p=>p.currency),account.currency])].flatMap(currency=>{
    const positions=dashboard.positions.filter(p=>p.accountId===account.id&&p.currency===currency);
    return positions.length?[{account:account.name,currency,count:positions.length,value:quoteStatus(positions,now)==='passed'?positions.reduce((s,p)=>s+(p.marketValue||0),0):null}]:[];
  }));
  return <section className="folio-panel"><div className="risk-section-heading"><strong>资本与现金约束</strong><span>同币种分别计量，不使用名义金额汇总</span></div>
    <RiskTable label="资本敞口" heads={['币种','持仓市值','账本现金','简化净资产','持仓 / 净资产','现金 / 净资产','限价买单待占款','待占款后现金','未定价买单']}>
      {capital.map(c=><tr key={c.currency}><td>{c.currency}</td><td>{n(c.invested)}</td><td className={c.cash<0?'negative':''}>{n(c.cash)}</td><td>{n(c.nav)}</td><td>{pct(c.grossExposurePct)}</td><td>{pct(c.cashPct)}</td><td>{n(c.knownCommitment)}</td><td className={c.cashAfterKnownOrders<0?'negative':''}>{n(c.cashAfterKnownOrders)}</td><td>{c.unpricedOrders}</td></tr>)}
    </RiskTable><p className="method-note">简化净资产=持仓市值+账本现金，非券商可用资金，不含未记账负债。净资产≤0时不计算比率。占款只包括已报/部分成交限价买单的未成交金额，未计费用。</p>
    <div className="risk-analysis-columns"><div><h3>市场分布</h3><RiskTable label="市场分布" heads={['币种','市场','证券数','市值','持仓权重']}>
      {groups.flatMap(g=>(['CN','HK','US'] as const).map(m=>{const rows=g.rows.filter(p=>p.market===m);return <tr key={`${g.currency}:${m}`}><td>{g.currency}</td><td>{m}</td><td>{rows.length}</td><td>{g.status==='passed'?n(rows.reduce((s,p)=>s+p.value,0)):'—'}</td><td>{g.status==='passed'?pct(rows.reduce((s,p)=>s+p.weight,0)):'—'}</td></tr>}))}</RiskTable></div>
      <div><h3>账户持仓分布</h3><RiskTable label="账户持仓分布" heads={['账户','币种','持仓笔数','持仓市值']}>{accountRows.map(r=><tr key={`${r.account}:${r.currency}`}><td>{r.account}</td><td>{r.currency}</td><td>{r.count}</td><td>{n(r.value)}</td></tr>)}</RiskTable></div></div>
  </section>;
}

export function DrawdownAnalysis({result}:{result:PortfolioPerformanceResult}) {
  const data=historyDiagnostics(result);
  const series=result.series;
  const min=Math.min(-1,...series.map(p=>p.drawdownPct));
  const line=series.map((p,i)=>`${50+(i/Math.max(1,series.length-1))*710},${25+p.drawdownPct/min*130}`).join(' ');
  return <div className="risk-analysis-section"><div className="risk-section-heading"><strong>回撤阶段与尾部样本</strong><span>窗口末回撤 {pct(data.currentDrawdownPct)} · 回本所需涨幅 {pct(data.recoveryNeededPct)}</span></div>
    <svg viewBox="0 0 800 200" className="risk-drawdown-chart" role="img" aria-label="历史模拟回撤曲线"><line x1="50" y1="25" x2="760" y2="25"/><line x1="50" y1="155" x2="760" y2="155"/><text x="4" y="29">0%</text><text x="4" y="157">{n(min)}%</text><polyline points={line}/><text x="50" y="185">{series[0]?.label}</text><text x="760" y="185" textAnchor="end">{series.at(-1)?.label}</text></svg>
    <div className="risk-analysis-columns"><div><h3>最深回撤阶段</h3><RiskTable label="回撤阶段" heads={['前高','谷底','恢复','深度','水下周数']}>
      {data.episodes.slice(0,8).map((e,i)=><tr key={i}><td>{e.peak}</td><td>{e.trough}</td><td>{e.recovery||'尚未恢复'}</td><td className="negative">{pct(e.depthPct)}</td><td>{e.weeks}</td></tr>)}</RiskTable>{!data.episodes.length&&<p className="method-note">该样本未观察到回撤，不代表未来无风险。</p>}</div>
      <div><h3>收益最低的 5 周</h3><RiskTable label="最差周" heads={['周','模拟收益']}>
        {data.worstWeeks.map(w=><tr key={w.label}><td>{w.label}</td><td className={w.returnPct<0?'negative':''}>{pct(w.returnPct)}</td></tr>)}</RiskTable></div></div><p className="method-note">仅分解当前权重模拟曲线；“水下周数”统计未恢复前高的观测周，不是交易日。窗口起点无更早峰值，不能推断区间外回撤。</p>
  </div>;
}

export function StressAnalysis({dashboard,now,shocks,onShocks}:{dashboard:PortfolioDashboard;now:number;shocks:Record<Market,number>;onShocks(value:Record<Market,number>):void}) {
  const scenarios=[...STRESS_SCENARIOS,{name:'自定义冲击',shocks}];
  const custom=scenarioImpact(dashboard,shocks,now);
  return <section className="folio-panel"><div className="risk-section-heading"><strong>确定性市场冲击</strong><span>情景假设，不是预测或自动交易指令</span></div><div className="risk-scenario-controls">{(['CN','HK','US'] as const).map(m=><label key={m}>{m} 价格冲击 / %<input type="number" min={-100} max={100} step={1} value={shocks[m]} onChange={e=>{const value=Number(e.target.value);if(Number.isFinite(value))onShocks({...shocks,[m]:Math.max(-100,Math.min(100,value))});}}/></label>)}</div>
    <RiskTable label="压力情景矩阵" heads={['情景','CN / HK / US','币种','持仓市值','损益金额','持仓损失率','净资产损失率']}>
      {scenarios.flatMap(s=>scenarioImpact(dashboard,s.shocks,now).map(row=><tr key={`${s.name}:${row.currency}`}><td>{s.name}</td><td>{s.shocks.CN}% / {s.shocks.HK}% / {s.shocks.US}%</td><td>{row.currency}</td><td>{n(row.invested)}</td><td className={row.pnl!=null&&row.pnl<0?'negative':''}>{n(row.pnl)}</td><td>{pct(row.lossOnInvestedPct)}</td><td>{pct(row.lossOnNavPct)}</td></tr>))}
    </RiskTable><h3>自定义冲击 · 证券损益分解</h3><RiskTable label="情景证券损益" heads={['证券','币种','市场','持仓权重','价格冲击','损益金额']}>
      {custom.flatMap(g=>g.rows.map(r=><tr key={`${g.currency}:${r.market}:${r.symbol}`}><td><strong>{r.name}</strong><small>{r.symbol}</small></td><td>{g.currency}</td><td>{r.market}</td><td>{pct(r.weight)}</td><td>{pct(r.shockPct)}</td><td className={r.pnl!=null&&r.pnl<0?'negative':''}>{n(r.pnl)}</td></tr>))}
    </RiskTable><p className="method-note">损益=证券市值×所在市场冲击；持仓损失率=−损益/持仓市值；净资产损失率=−损益/(持仓市值+账本现金)。现金保持不变，净资产≤0不计算比率；负损失率代表收益。不含汇率、相关性变化、期权非线性或冲击成本。参数为本地情景，当前风险评估留档不包含自定义情景。</p></section>;
}

export function LiquidityEvidence({dashboard,now}:{dashboard:PortfolioDashboard;now:number}) {
  return <section className="folio-panel"><div className="risk-section-heading"><strong>持仓可退出性 · 证据清单</strong><span>缺少成交额、盘口、可卖数量时不输出退出天数</span></div>
    <RiskTable label="流动性证据" heads={['证券 / 账户','币种','持有数量','市值','报价时间','行情状态','ADV20','可卖数量','退出天数']}>
      {dashboard.positions.map(p=><tr key={`${p.accountId}:${p.market}:${p.symbol}`}><td><strong>{p.name}</strong><small>{p.market}:{p.symbol} · {p.accountId}</small></td><td>{p.currency}</td><td>{n(p.quantity)}</td><td>{quoteStatus([p],now)==='passed'?n(p.marketValue):'—'}</td><td>{p.quoteAsOf?new Date(p.quoteAsOf).toLocaleString('zh-CN'):'未提供'}</td><td>{RISK_LABELS[quoteStatus([p],now)]}</td><td>未接入</td><td>未接入</td><td>不可计算</td></tr>)}
    </RiskTable><h3>正式评估所需证据</h3><RiskTable label="流动性方法要求" heads={['风险维度','必要字段','计算 / 约束','当前结论']}>
      <tr><td>容量</td><td>同币种日成交额、20 个交易日、停牌日</td><td>持仓市值 / (ADV20 × 参与率)</td><td>缺数据，不使用周线成交量替代</td></tr><tr><td>立即变现</td><td>可卖数量、冻结数量、买盘深度、报价时间</td><td>逐档可成交量和价差</td><td>未评估</td></tr><tr><td>融资与现金</td><td>待成交委托、保证金、负债到期</td><td>现金缺口与到期梯度</td><td>仅账本现金与已知限价占款可核验</td></tr></RiskTable>
    <p className="method-note">ADV 是日均成交额。即使补齐 ADV，退出天数也仅是给定参与率的容量估计，不保证能成交；还需交易限制、停牌和价格冲击信息。</p></section>;
}
