export const INVESTMENT_DOMAIN_IDS = [
  "global-intelligence",
  "fundamentals",
  "policy-intelligence",
  "capital-flow",
  "market-surface",
  "industry-research",
  "equity-research",
  "fund-research",
  "asset-allocation",
  "trading",
  "strategy-research",
  "risk-management",
  "quant-research",
  "investment-committee",
  "creator-studio",
  "deepsee",
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
    id: "global-intelligence",
    name: "全球",
    order: 0,
    description: "全球态势、新闻、地缘冲突、海外专题、事件与催化剂。",
    icon: "research",
  },
  {
    id: "fundamentals",
    name: "宏观",
    order: 10,
    description: "周期叠加、经济基本面、增长通胀、金融条件与经济预测。",
    icon: "research",
  },
  {
    id: "policy-intelligence",
    name: "政策",
    order: 20,
    description: "政策日历、政策流、政策量级、历史对比与影响解读。",
    icon: "research",
  },
  {
    id: "capital-flow",
    name: "资金",
    order: 30,
    description: "跨境资金、流动性、ETF 与个股资金、筹码及风险偏好。",
    icon: "market",
  },
  {
    id: "market-surface",
    name: "市场",
    order: 40,
    description: "行情、市场复盘、云图、技术结构、强弱、宽度与情绪。",
    icon: "market",
  },
  {
    id: "industry-research",
    name: "行业",
    order: 50,
    description: "产业链、行业比较、景气选择、资金扩散与行业 ETF 轮动。",
    icon: "research",
  },
  {
    id: "equity-research",
    name: "公司",
    order: 60,
    description: "公司基本面、财报、投资逻辑、同业、估值与研究档案。",
    icon: "research",
  },
  {
    id: "fund-research",
    name: "基金",
    order: 70,
    description: "公募基金、ETF、基金经理、同类比较、评价与业绩归因。",
    icon: "research",
  },
  {
    id: "asset-allocation",
    name: "配置",
    order: 80,
    description: "战略资产配置、目标权重、研究组合、再平衡与绩效归因。",
    icon: "quant",
  },
  {
    id: "trading",
    name: "交易",
    order: 90,
    description: "战术择时、交易计划、纸面执行、复盘回放与执行记录。",
    icon: "trading",
  },
  {
    id: "strategy-research",
    name: "策略",
    order: 100,
    description: "研究线索、条件筛选、策略验证、候选池与观察组合。",
    icon: "quant",
  },
  {
    id: "risk-management",
    name: "风险",
    order: 110,
    description: "集中度、暴露、相关性、回撤、压力测试与风险贡献。",
    icon: "trading",
  },
  {
    id: "quant-research",
    name: "量化",
    order: 120,
    description: "因子、策略实验、回测、相关性分析与可复现研究账本。",
    icon: "quant",
  },
  {
    id: "investment-committee",
    name: "投决",
    order: 130,
    description: "研究结论收敛、投委讨论、决策记录、反方意见与复核。",
    icon: "research",
  },
  {
    id: "creator-studio",
    name: "创作",
    order: 140,
    description: "内容采集、研究转写、多媒体生产、发布与传播复盘。",
    icon: "module",
  },
  {
    id: "deepsee",
    name: "深瞳",
    order: 150,
    description: "消息、邮件、会议、自媒体与外部信息触达分析。",
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
