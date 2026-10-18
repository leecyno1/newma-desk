import { ArrowRight, GitBranch } from "lucide-react";
import type { buildInvestmentTransmission } from "./investment";

export function InvestmentTransmission({ research }: { research: NonNullable<ReturnType<typeof buildInvestmentTransmission>> }) {
  return <section className="intel-investment-transmission" aria-label="投资传导研究">
    <header><span><GitBranch size={14} />投资传导研究</span><small>假设 · 非交易建议</small></header>
    <p className="intel-evidence-gate">{research.evidenceGate}</p>
    {research.pathways.map((pathway) => <article key={pathway.routeId}>
      <div className="intel-transmission-path"><strong>{pathway.association}</strong><ArrowRight size={12} /><strong>{pathway.route}</strong><ArrowRight size={12} /><span>{[...pathway.commodities, ...pathway.industries].join(" / ") || "资产映射待补充"}</span></div>
      <p>{pathway.hypothesis}</p>
      <dl>
        <div><dt>验证指标</dt><dd>{pathway.validationIndicators.join("、") || "暂无已接入指标"}</dd></div>
        <div><dt>市场观测</dt><dd>{pathway.observations.length ? pathway.observations.map((item) => `${item.label} ${item.value}${item.unit} · ${item.timestamp || "时间未知"} · ${item.reason}`).join("；") : "暂无对应行情证据，不能判定市场已确认"}</dd></div>
        <div><dt>撤销条件</dt><dd>{pathway.invalidation}</dd></div>
      </dl>
    </article>)}
    <p>{research.gaps.join("；")}。</p>
    <small>{research.semantics}</small>
  </section>;
}
