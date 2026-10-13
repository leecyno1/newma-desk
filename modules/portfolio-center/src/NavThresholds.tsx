import { RiskTable } from './RiskAnalytics';

export type NavThresholdData={warningLine:number|null;floor:number|null;rows:Array<{label:string;nav:number|null;warningHeadroom:number|null;floorHeadroom:number|null;status:string}>};
export const thresholdLabels:Record<string,string>={unassessed:'未评估',unconfigured:'未设阈值',floor_breached:'跌破底线',floor_reached:'触及底线',warning:'触发预警',above_lines:'高于已设阈值'};
const amount=(n:number|null)=>n==null?'未设置 / 未评估':n.toLocaleString('zh-CN',{maximumFractionDigits:2});

export function NavThresholds({data,currency}:{data?:NavThresholdData;currency:string}){
  return <section id="diagnosis-thresholds" tabIndex={-1} aria-label="净值分级预警">
    <h3>净值分级预警</h3>
    {!data?<p>此版本尚无分级预警结果；请编辑阈值并另存，或按最新口径重评估。旧版不会自动改写。</p>:<>
      <p className="method-note">预警线 {amount(data.warningLine)} · 底线 {amount(data.floor)} {currency}。均为净资产金额，不是单位净值、比例或合同自动校验。等于阈值即提示；跌破底线优先于预警。缺估值不判安全。</p>
      <RiskTable label="净值分级预警明细" heads={['依据','净资产','距预警线余量','距底线余量','判断']}>
        {data.rows.map(row=><tr key={row.label}><td>{row.label}</td><td>{amount(row.nav)}</td><td>{amount(row.warningHeadroom)}</td><td>{amount(row.floorHeadroom)}</td><td><span className={['floor_breached','floor_reached','warning'].includes(row.status)?'risk-threshold-alert':''}>{thresholdLabels[row.status]||'未评估'}</span></td></tr>)}
      </RiskTable>
      <p className="method-note">首行为导入快照，其余为假设情景；情景触线不是当前已发生损失。修改阈值不减少实际风险，须保留旧版并复核依据。这里只提示，不自动减仓、止损或发送通知。</p>
    </>}
  </section>;
}
