import { NextRequest } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface AnalysisRequest {
  type: 'fund' | 'manager' | 'comparison'
  targetId: string
  compareId?: string
  includeReports?: boolean
  customPrompt?: string
  purchasePlan?: 'lump_sum' | 'sip'
  plannedAmount?: number | string | null
  returnTo?: string
}

type ManagerFund = {
  wind_code?: string
  name?: string
  fund_name?: string
  type?: string
  start_date?: string | null
  end_date?: string | null
}

type ManagerDetail = {
  id?: string
  name?: string
  company?: string | null
  education?: string | null
  workYears?: number | null
  managementYears?: number | null
  fundCount?: number
  currentFunds?: string[]
  funds?: ManagerFund[]
}

type ScorePayload = {
  finalScore?: {
    totalScore?: number
    grade?: string
    summary?: string
    scores?: Array<{ dimension?: string; score?: number; details?: string }>
  }
  buyBeforeBoundary?: {
    label?: string
    detail?: string
    requiredGates?: string[]
  }
}

function normalizePurchasePlan(value: unknown): 'lump_sum' | 'sip' {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function defaultPlannedAmountForPlan(purchasePlan: 'lump_sum' | 'sip') {
  return purchasePlan === 'lump_sum' ? 10000 : 1000
}

function normalizePlannedAmount(value: unknown, purchasePlan: 'lump_sum' | 'sip') {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount) : defaultPlannedAmountForPlan(purchasePlan)
}

function purchasePlanLabel(value: 'lump_sum' | 'sip') {
  return value === 'lump_sum' ? '一次性配置' : '定投'
}

function purchaseContextParams(purchasePlan: 'lump_sum' | 'sip', plannedAmount: number) {
  const amount = String(plannedAmount)
  return new URLSearchParams({
    purchasePlan,
    plannedAmount: amount,
    [purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: amount,
  }).toString()
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function safeReturnPath(returnTo: unknown) {
  return typeof returnTo === 'string' && returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : ''
}

function formatDate(value?: string | null) {
  if (!value) return '缺失'
  if (/^\d{8}$/u.test(value)) return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`
  return value
}

function buildManagerMemo(manager: ManagerDetail, scorePayload: ScorePayload, requestUrl: string, purchasePlan: 'lump_sum' | 'sip', plannedAmount: number, sourceReturnHref = '') {
  const funds = manager.funds || []
  const codes = Array.from(new Set(funds.map((fund) => fund.wind_code).filter((code): code is string => Boolean(code))))
  const activeFunds = funds.filter((fund) => !fund.end_date)
  const compareCodes = (activeFunds.length >= 2 ? activeFunds : funds).map((fund) => fund.wind_code).filter((code): code is string => Boolean(code)).slice(0, 8)
  const score = scorePayload.finalScore
  const scoreBoundary = scorePayload.buyBeforeBoundary
  const managerId = manager.id || manager.name || ''
  const purchaseContextQuery = purchaseContextParams(purchasePlan, plannedAmount)
  const managerHref = sourceReturnHref.startsWith('/managers/')
    ? sourceReturnHref
    : `/managers/${encodeURIComponent(managerId)}?${purchaseContextQuery}`
  const compareHref = compareCodes.length >= 2
    ? appendReturnTo(`/analysis/comparison?codes=${encodeURIComponent(compareCodes.join(','))}&profile=balanced&horizon=1to3y&${purchaseContextQuery}&autoReplay=1`, managerHref)
    : ''
  const salesRuleParams = new URLSearchParams(purchaseContextQuery)
  if (codes.length > 0) salesRuleParams.set('codes', codes.slice(0, 30).join(','))
  const salesRulesHref = codes.length > 0
    ? appendReturnTo(materialEvidenceHref(salesRuleParams), managerHref)
    : appendReturnTo(materialEvidenceHref(new URLSearchParams(purchaseContextQuery)), managerHref)
  const origin = new URL(requestUrl).origin
  const fundRows = funds.slice(0, 20).map((fund, index) => {
    const code = fund.wind_code || ''
    const name = fund.name || fund.fund_name || code || `基金 ${index + 1}`
    const status = fund.end_date ? '历史任职' : '未见离任'
    return `| ${index + 1} | ${name} | ${code || '缺失'} | ${fund.type || '待补'} | ${formatDate(fund.start_date)} | ${formatDate(fund.end_date)} | ${status} |`
  }).join('\n')
  const scoreRows = (score?.scores || []).map((item) =>
    `- ${item.dimension || '评分维度'}：${Number(item.score ?? 0).toFixed(1)}；${item.details || '证据待补'}`,
  ).join('\n')
  const scoreBoundaryGates = (scoreBoundary?.requiredGates || [])
    .map((gate) => `  - ${gate}`)
    .join('\n')

  return `# ${manager.name || managerId} · 基金经理研究备忘录

- 生成方式：本地确定性证据备忘录
- 数据来源：本地 Tushare fund_manager 同步记录、基金主数据、经理评分 API
- 研究方式口径：${purchasePlanLabel(purchasePlan)}
- 计划金额：${plannedAmount.toLocaleString('zh-CN')} 元
- 经理 ID：${managerId || '缺失'}
- 所属公司：${manager.company || '待补'}
- 学历：${manager.education || '待补'}
- 管理年限：${manager.managementYears ? `${Number(manager.managementYears).toFixed(1)} 年` : '待补'}
- 任职记录数：${manager.fundCount ?? funds.length}
- 未见离任基金数：${activeFunds.length}

## 经理评分

- 综合评分：${score?.totalScore ?? '待补'}
- 评级：${score?.grade || '待补'}
- 结论：${score?.summary || '评分证据不足，不能直接形成正式研究结论。'}
- 评分边界：${scoreBoundary?.label || '评分仅用于研究排序'}

${scoreRows || '- 评分维度待补'}

## 管理基金任职记录

| # | 基金 | 代码 | 类型 | 开始 | 结束 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
${fundRows || '| - | 暂无本地任职记录 | - | - | - | - | - |'}

## 研究使用边界

- 该备忘录只评价经理任职记录和可核验证据，不能替代单只基金研究复核。
- ${scoreBoundary?.detail || '评分只用于研究排序，不能替代销售规则、风险等级、费用和研究复核报告门禁。'}
${scoreBoundaryGates ? `- 评分后仍需通过：\n${scoreBoundaryGates}` : '- 评分后仍需通过：销售规则硬缺口、R1-R5 适当性、费用与赎回规则、限购/起购或定投规则、净值回放和正式研究复核报告'}
- “未见离任”只代表本地 Tushare 记录未给出结束日期，形成研究结论前仍需复核基金公告。
- 经理评价不能替代单只基金研究核查；必须继续检查基金费率、申赎状态、限购、风险等级和同类比较。
- 若销售规则缺失，系统应保持“先补证再判断”，不得输出正式研究结论。

## 下一步入口

- 经理详情：${origin}${managerHref}
- 批量补销售规则：${origin}${salesRulesHref}
${compareHref ? `- 横向对比管理基金：${origin}${compareHref}` : '- 横向对比管理基金：可比基金不足，暂不生成链接'}
`
}

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder()

  const stream = new ReadableStream({
    async start(controller) {
      const send = (payload: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`))
      }

      try {
        const body: AnalysisRequest = await request.json()
        const { type, targetId } = body
        const purchasePlan = normalizePurchasePlan(body.purchasePlan)
        const plannedAmount = normalizePlannedAmount(body.plannedAmount, purchasePlan)

        send({ type: 'start', message: '开始加载研究对象...' })

        if (type === 'manager') {
          send({ type: 'progress', message: '正在读取本地基金经理任职记录...' })
          const origin = new URL(request.url).origin
          const managerResponse = await fetch(`${origin}/api/managers/${encodeURIComponent(targetId)}`, {
            cache: 'no-store',
          })
          const managerPayload = await managerResponse.json().catch(() => ({}))
          if (!managerResponse.ok) {
            throw new Error(managerPayload.error || '基金经理不存在，请先同步经理数据')
          }

          send({ type: 'progress', message: '正在计算基金经理评分...' })
          const scoreResponse = await fetch(`${origin}/api/scores?targetType=manager&targetId=${encodeURIComponent(targetId)}`, {
            cache: 'no-store',
          })
          const scorePayload = await scoreResponse.json().catch(() => ({}))
          if (!scoreResponse.ok) {
            throw new Error(scorePayload.error || '基金经理评分失败')
          }

          const report = buildManagerMemo(managerPayload, scorePayload, request.url, purchasePlan, plannedAmount, safeReturnPath(body.returnTo))
          send({ type: 'progress', message: '本地经理研究备忘录已生成，正在输出...' })
          for (const paragraph of report.split('\n\n')) {
            send({ type: 'content', text: `${paragraph}\n\n` })
          }
          send({
            type: 'complete',
            message: '本地经理研究备忘录生成完成',
            reportId: null,
          })
          controller.close()
          return
        }

        if (type !== 'fund') {
          throw new Error('当前浏览器闭环支持基金分析和基金经理分析')
        }

        send({ type: 'progress', message: '正在从本地 PostgreSQL 读取基金数据...' })
        const fundResponse = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(targetId)}`, {
          cache: 'no-store',
        })
        const fundPayload = await fundResponse.json().catch(() => ({}))
        if (!fundResponse.ok) {
          throw new Error(fundPayload.detail || fundPayload.error || '基金不存在，请先同步该基金')
        }

        send({ type: 'progress', message: '真实基金数据加载完成，正在生成研究报告...' })
        const reportUrl = new URL(`/api/reports/fund/${encodeURIComponent(targetId)}`, backendApiBaseUrl)
        reportUrl.searchParams.set('include_research', String(body.includeReports ?? true))
        reportUrl.searchParams.set('report_depth', 'standard')
        reportUrl.searchParams.set('purchase_plan', purchasePlan)
        reportUrl.searchParams.set('planned_amount', String(plannedAmount))
        const reportResponse = await fetch(reportUrl, {
          method: 'POST',
          cache: 'no-store',
        })
        const reportPayload = await reportResponse.json().catch(() => ({}))
        if (!reportResponse.ok) {
          throw new Error(reportPayload.detail || reportPayload.error || '报告生成失败')
        }

        const report = String(reportPayload.report || '').trim()
        if (!report) {
          throw new Error('模型没有返回报告内容')
        }
        if (/当前使用模拟数据|配置模型 API Key 后/.test(report)) {
          throw new Error('后端 LLM API Key 未配置，已阻止输出模拟报告')
        }

        const generationMode = reportPayload.metadata?.mode || reportPayload.metadata?.data_sources?.generation_mode || 'unknown'
        const generationLabel = generationMode === 'deterministic_evidence_backed' ? '本地证据报告' : '模型增强报告'

        send({ type: 'progress', message: `${generationLabel}已生成并写入本地数据库，正在输出...` })
        for (const paragraph of report.split('\n\n')) {
          send({ type: 'content', text: `${paragraph}\n\n` })
        }

        send({
          type: 'complete',
          message: `${generationLabel}生成完成`,
          reportId: reportPayload.id || reportPayload.metadata?.report_id || null,
        })
        controller.close()
      } catch (error) {
        console.error('生成分析报告失败:', error)
        send({
          type: 'error',
          message: error instanceof Error ? error.message : '生成失败',
        })
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
}
