import { RiskTable } from './RiskAnalytics';

export type LiquidityPlanData = {
  accountReservesIncluded?:boolean;
  deadline:string|null;
  items:Array<{name:string;symbol:string;holdingAccount:string;currency:string;amount:number|null;baseAmount:number|null;date:string|null;receivingAccount:string;source:string;status:string;note:string}>;
  projections:Array<{scenario:string;account:string;currentStressRemaining:number|null;plannedReceipts:number;conditionalRemaining:number|null}>;
  basis:string;
};
const number=(value:number|null)=>value==null?'未评估':value.toLocaleString('zh-CN',{maximumFractionDigits:2});
const states:Record<string,string>={incomplete:'资料未齐',reconcile:'需核对是否已到账',no_deadline:'未设观察日',late:'晚于观察日',account_unverified:'账户或币种待核对',conditional:'仅条件纳入'};

export function LiquidityPlan({data,currency}:{data:LiquidityPlanData;currency:string}) {
  if(!data.items.length&&!data.deadline)return <p className="method-note">尚未提供资金到账计划；当前只评估现有现金，不推测基金或债券的变现速度。</p>;
  return <section aria-label="资金到账计划">
    <h3>资金到账计划 · 不计入现有现金</h3>
    <p className="method-note">资金观察日：{data.deadline||'未设置'}。预计变现不增加当前净资产；未来到账也不能自动覆盖此前的追保。</p>
    {data.items.length?<RiskTable label="资金到账计划明细" heads={['持仓 / 原账户','预计净额 / 原币','预计到账日','收款账户','处理状态','依据与限制']}>
      {data.items.map((p,i)=><tr key={i}><td>{p.name}<small>{p.symbol} · {p.holdingAccount}</small></td><td>{number(p.amount)} {p.currency}</td><td>{p.date||'未提供'}</td><td>{p.receivingAccount||'未提供'}</td><td>{states[p.status]||p.status}</td><td>{p.note}<small>{p.source||'未提供到账依据'}</small></td></tr>)}
    </RiskTable>:<p>已设观察日，但尚未提供金额、日期及账户明确的到账计划。</p>}
    {data.projections.length>0&&<><h3>观察日的条件余额 · 假设计划全额如期到账</h3><RiskTable label="条件到账现金余额" heads={['情景 / 收款账户',data.accountReservesIncluded?'扣期货亏损及账户预留后':'现有现金扣期货亏损后','假设如期到账','条件余额（非已落实资金）']}>
      {data.projections.map((p,i)=><tr key={i}><td>{p.scenario}<small>{p.account}</small></td><td>{number(p.currentStressRemaining)}</td><td>{number(p.plannedReceipts)}</td><td>{number(p.conditionalRemaining)}</td></tr>)}
    </RiskTable><p className="method-note">金额为 {currency} 等值，{data.accountReservesIncluded?"已扣该账户已分配预留；组合未分配部分仍须另留":"尚未分摊近期资金预留"}；仅按列示计划测算，不代表变现后的组合风险或可立即充抵的保证金。上方当前现金预警仍有效。</p></>}
    <p className="method-note">{data.basis}</p>
  </section>;
}
