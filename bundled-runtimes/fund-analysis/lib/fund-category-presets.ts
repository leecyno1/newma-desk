/**
 * 基金分类预设 — 区分主动研究（primary）和指数工具（index_tool）
 *
 * - primary: 需要深度研究的主动管理基金，是选基的核心目标
 * - index_tool: 被动指数基金，仅比较跟踪误差/费率/规模，不做选基推荐
 */

export type FundCategoryPreset = {
  category: string
  label: string
  description: string
  mark: string
  tier: 'primary' | 'index_tool'
}

export const fundCategoryPresets: readonly FundCategoryPreset[] = [
  // ─── 主动研究：选基精选的核心目标 ───
  { category: '主动权益-沪深300参考', label: '主动权益（大盘）', description: '主动选股，以沪深300为业绩基准', mark: '01', tier: 'primary' },
  { category: '混合型-偏股配置', label: '偏股混合', description: '股票为主、配置灵活的主动基金', mark: '02', tier: 'primary' },
  { category: '混合型-平衡配置', label: '平衡混合', description: '股债均衡的主动配置基金', mark: '03', tier: 'primary' },
  { category: '混合型-偏债配置', label: '偏债混合', description: '债券为主、少量权益增强', mark: '04', tier: 'primary' },
  { category: '主动权益-行业/消费主题', label: '消费主题', description: '聚焦消费行业的主动选股', mark: '05', tier: 'primary' },
  { category: '固收-中证全债参考', label: '纯债/固收', description: '债券收益和回撤控制', mark: '06', tier: 'primary' },
  { category: '固收-中债综合指数·全价·全期限参考', label: '中长期纯债', description: '久期策略、信用下沉', mark: '07', tier: 'primary' },
  { category: '债券型-含权益配置', label: '固收+', description: '债底+转债/权益增强', mark: '08', tier: 'primary' },
  { category: 'FOF-偏股配置', label: '偏股 FOF', description: '通过基金组合参与权益', mark: '09', tier: 'primary' },
  { category: 'FOF-平衡配置', label: '平衡 FOF', description: '权益与固收均衡配置', mark: '10', tier: 'primary' },
  { category: 'FOF-偏债配置', label: '偏债 FOF', description: '固收为主、兼顾增强', mark: '11', tier: 'primary' },

  // ─── 指数工具箱：被动跟踪，仅评判 TE/IR/费率 ───
  { category: '指数-沪深300', label: '沪深300 ETF', description: '跟踪误差 · 费率 · 规模', mark: 'I1', tier: 'index_tool' },
  { category: '指数-中证A500', label: '中证A500 ETF', description: '跟踪误差 · 费率 · 规模', mark: 'I2', tier: 'index_tool' },
  { category: '指数-中证500', label: '中证500 ETF', description: '跟踪误差 · 费率 · 规模', mark: 'I3', tier: 'index_tool' },
  { category: '指数-创业板指', label: '创业板 ETF', description: '跟踪误差 · 费率 · 规模', mark: 'I4', tier: 'index_tool' },
  { category: '指数增强-沪深300', label: '沪深300 增强', description: '超额收益 · IR · TE', mark: 'I5', tier: 'index_tool' },
  { category: 'QDII-人民币计价纳斯达克100指数', label: '纳指100 QDII', description: '跟踪误差 · 费率 · 汇率', mark: 'I6', tier: 'index_tool' },
  { category: '货币-现金管理', label: '货币基金', description: '7 日年化 · 万份收益 · 规模', mark: 'I7', tier: 'index_tool' },
] as const

/** 只返回主动研究类别 */
export const primaryPresets = fundCategoryPresets.filter((p) => p.tier === 'primary')

/** 只返回指数工具类别 */
export const indexToolPresets = fundCategoryPresets.filter((p) => p.tier === 'index_tool')
