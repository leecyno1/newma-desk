import { NextRequest, NextResponse } from 'next/server'
import { countSalesRules, getMergedSalesRulesByWindCodes, listSalesRules, upsertSalesRule, type SalesRuleInput } from '@/lib/sales-rules'
import { isValidWindCode, validateSalesRule } from '@/lib/sales-rule-validation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_BULK_RULES = 500

function normalizeRules(body: unknown) {
  if (Array.isArray(body)) return body
  if (body && typeof body === 'object' && Array.isArray((body as Record<string, unknown>).rules)) {
    return (body as Record<string, unknown>).rules as unknown[]
  }
  return []
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const platform = searchParams.get('platform') || undefined
    const limit = Number(searchParams.get('limit') || 100)
    const codes = searchParams.get('codes')
    if (codes) {
      const requestedCodes = Array.from(new Set(
        codes
          .split(',')
          .map((code) => code.trim().toUpperCase())
          .filter(isValidWindCode),
      )).slice(0, MAX_BULK_RULES)
      const ruleMap = await getMergedSalesRulesByWindCodes(requestedCodes)
      const rules = requestedCodes
        .map((code) => ruleMap.get(code))
        .filter((rule): rule is NonNullable<typeof rule> => Boolean(rule))
      return NextResponse.json({
        total: rules.length,
        requestedCount: requestedCodes.length,
        missingCodes: requestedCodes.filter((code) => !ruleMap.has(code)),
        rules,
        source: 'local.postgres.fund_sales_rules.merged_by_code',
        usage: {
          get: 'GET /api/evidence-coverage/materials?codes=000001.OF,000002.OF',
          post: 'POST /api/evidence-coverage/materials with { rules: [{ windCode, platform, purchaseStatus, purchaseFeeRate, salesServiceFeeRate, redemptionFeeRules, minPurchaseAmount, minSipAmount, dailyLimitAmount, riskLevel, supportsSip, sourceUpdatedAt, notes }] }',
          maxBatchSize: MAX_BULK_RULES,
        },
      })
    }
    const [total, rules] = await Promise.all([
      countSalesRules(platform),
      listSalesRules(limit, platform),
    ])

    return NextResponse.json({
      total,
      rules,
      source: 'local.postgres.fund_sales_rules',
      usage: {
        post: 'POST /api/evidence-coverage/materials with { rules: [{ windCode, platform, purchaseStatus, purchaseFeeRate, salesServiceFeeRate, redemptionFeeRules, minPurchaseAmount, minSipAmount, dailyLimitAmount, riskLevel, supportsSip, sourceUpdatedAt, notes }] }',
        maxBatchSize: MAX_BULK_RULES,
      },
    })
  } catch (error) {
    console.error('读取材料核验列表失败:', error)
    return NextResponse.json({ error: '读取材料核验列表失败' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null)
    const rules = normalizeRules(body)
    if (rules.length === 0) {
      return NextResponse.json({ error: '请求体必须包含 rules 数组' }, { status: 400 })
    }
    if (rules.length > MAX_BULK_RULES) {
      return NextResponse.json({ error: `单次最多导入 ${MAX_BULK_RULES} 条材料核验记录` }, { status: 400 })
    }

    const saved = []
    const failed = []
    for (const item of rules) {
      const rule = item as Record<string, unknown>
      if (!isValidWindCode(rule.windCode)) {
        failed.push({ windCode: rule.windCode || null, error: 'windCode 格式不正确' })
        continue
      }
      const validationErrors = validateSalesRule(rule)
      if (validationErrors.length) {
        failed.push({ windCode: rule.windCode || null, error: validationErrors.join('；') })
        continue
      }
      try {
        const normalizedRule = {
          ...rule,
          windCode: String(rule.windCode).trim().toUpperCase(),
          riskLevel: typeof rule.riskLevel === 'string' ? rule.riskLevel.trim().toUpperCase() : rule.riskLevel,
        } as SalesRuleInput
        saved.push(await upsertSalesRule(String(rule.windCode).trim().toUpperCase(), normalizedRule, String(rule.platform || 'manual')))
      } catch (error) {
        failed.push({
          windCode: rule.windCode,
          error: error instanceof Error ? error.message : '保存失败',
        })
      }
    }

    return NextResponse.json({
      savedCount: saved.length,
      failedCount: failed.length,
      saved,
      failed,
      source: 'local.postgres.fund_sales_rules',
    }, { status: saved.length === 0 && failed.length > 0 ? 422 : 200 })
  } catch (error) {
    console.error('批量保存材料核验记录失败:', error)
    return NextResponse.json({ error: '批量保存材料核验记录失败' }, { status: 500 })
  }
}
