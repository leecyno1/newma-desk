export const RISK_PAGES = [
  { view: 'overview', id: 'portfolio-risk', label: '风险总览' },
  { view: 'limits', id: 'portfolio-risk-limits', label: '风险限额' },
  { view: 'concentration', id: 'portfolio-risk-concentration', label: '集中度' },
  { view: 'exposure', id: 'portfolio-risk-exposure', label: '市场 / 币种暴露' },
  { view: 'drawdown', id: 'portfolio-risk-drawdown', label: '回撤与 VaR' },
  { view: 'liquidity', id: 'portfolio-risk-liquidity', label: '流动性' },
  { view: 'stress', id: 'portfolio-risk-stress', label: '压力测试' },
  { view: 'alerts', id: 'portfolio-risk-alerts', label: '预警' },
  { view: 'actions', id: 'portfolio-risk-actions', label: '处置记录' },
] as const;
export type RiskViewId = typeof RISK_PAGES[number]['view'];
