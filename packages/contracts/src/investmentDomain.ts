export const INVESTMENT_DOMAIN_IDS = [
  "event-intelligence",
  "market-surface",
  "fundamentals",
  "global-intelligence",
  "capital-flow",
  "cycle-research",
  "asset-allocation",
  "tactical-timing",
  "equity-research",
  "fund-research",
  "bond-research",
  "quant-research",
  "investment-committee",
  "trading-risk-portfolio",
  "other",
] as const;

export type InvestmentDomainId = (typeof INVESTMENT_DOMAIN_IDS)[number];

export interface InvestmentDomainDefinition {
  id: InvestmentDomainId;
  name: string;
  order: number;
  description: string;
  icon: "market" | "research" | "quant" | "trading" | "module";
}

export const INVESTMENT_DOMAINS: readonly InvestmentDomainDefinition[] = [
  {
    id: "event-intelligence",
    name: "情报",
    order: 0,
    description: "全球态势、新闻、政策、冲突、灾害、舆情与市场异常事件。",
    icon: "research",
  },
  {
    id: "market-surface",
    name: "市场",
    order: 10,
    description: "股票、债券及其他交易市场的行情监控、看盘、扫描与回放。",
    icon: "market",
  },
  {
    id: "fundamentals",
    name: "宏观面",
    order: 20,
    description: "经济数据、宏观指标、行业、产业链与宏观事件。",
    icon: "research",
  },
  {
    id: "global-intelligence",
    name: "海外面",
    order: 30,
    description: "海外流动性、地缘政治、军事冲突、科技与全球市场研究。",
    icon: "research",
  },
  {
    id: "capital-flow",
    name: "资金面",
    order: 40,
    description: "资金流向、筹码、龙虎榜、情绪指标与技术结构。",
    icon: "market",
  },
  {
    id: "cycle-research",
    name: "周期研究",
    order: 60,
    description: "七周期及其扩展周期框架研究。",
    icon: "research",
  },
  {
    id: "asset-allocation",
    name: "资产配置",
    order: 70,
    description: "均值方差、Black-Litterman、风险评价、再平衡与目标波动率。",
    icon: "quant",
  },
  {
    id: "tactical-timing",
    name: "战术择时",
    order: 80,
    description: "行业比较、行业轮动、择时与 ETF 轮动。",
    icon: "quant",
  },
  {
    id: "equity-research",
    name: "个股研究",
    order: 90,
    description: "选股、公司基本面、量化选股、财报、同业与估值研究。",
    icon: "research",
  },
  {
    id: "fund-research",
    name: "基金研究",
    order: 100,
    description: "公募基金、ETF、基金经理与产品比较研究。",
    icon: "research",
  },
  {
    id: "bond-research",
    name: "债券研究",
    order: 110,
    description: "利率、信用、可转债与固定收益研究。",
    icon: "research",
  },
  {
    id: "quant-research",
    name: "量化研究",
    order: 120,
    description: "因子、策略、回测、相关性与量化实验。",
    icon: "quant",
  },
  {
    id: "investment-committee",
    name: "投决会",
    order: 130,
    description: "研究结论收敛、投委讨论、决策记录与复核。",
    icon: "research",
  },
  {
    id: "trading-risk-portfolio",
    name: "交易、风控与组合管理",
    order: 140,
    description: "交易执行、风险控制、持仓、组合管理与绩效归因。",
    icon: "trading",
  },
  {
    id: "other",
    name: "其他",
    order: 150,
    description: "尚未归入核心投研流程的管理工具与扩展能力。",
    icon: "module",
  },
] as const;

const INVESTMENT_DOMAIN_ID_SET = new Set<string>(INVESTMENT_DOMAIN_IDS);

export function isInvestmentDomainId(value: string): value is InvestmentDomainId {
  return INVESTMENT_DOMAIN_ID_SET.has(value);
}

export function investmentDomainProject(domain: InvestmentDomainDefinition) {
  return {
    id: domain.id,
    name: domain.name,
    order: domain.order,
    description: domain.description,
    logo: { type: "letter" as const, text: Array.from(domain.name).slice(0, 2).join("") },
  };
}
