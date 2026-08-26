export type ShareClassFundInput = {
  windCode?: string | null
  wind_code?: string | null
  name?: string | null
  type?: string | null
}

export type ShareClassInfo = {
  baseName: string
  classType: string
  siblingCount: number
  siblingCodes: string[]
  siblingNames: string[]
  hint: string
  warnings: string[]
}

function fundCode(fund: ShareClassFundInput) {
  return String(fund.windCode || fund.wind_code || '').trim()
}

function fundName(fund: ShareClassFundInput) {
  return String(fund.name || '').trim()
}

export function normalizeShareClassBaseName(name: string | null | undefined) {
  return String(name || '')
    .trim()
    .replace(/[（(]\s*(A|B|C|D|E|I|Y|H|人民币|美元现汇|美元现钞)\s*[）)]$/iu, '')
    .replace(/\s*(A|B|C|D|E|I|Y|H)类?$/iu, '')
    .replace(/\s*(人民币|美元现汇|美元现钞)$/u, '')
    .replace(/\s+/gu, '')
}

export function inferShareClass(name: string | null | undefined) {
  const text = String(name || '').trim()
  const bracketMatch = text.match(/[（(]\s*(A|B|C|D|E|I|Y|H|人民币|美元现汇|美元现钞)\s*[）)]$/iu)
  if (bracketMatch) return bracketMatch[1].toUpperCase()
  const classMatch = text.match(/\s*(A|B|C|D|E|I|Y|H)类?$/iu)
  if (classMatch) return classMatch[1].toUpperCase()
  const currencyMatch = text.match(/\s*(人民币|美元现汇|美元现钞)$/u)
  if (currencyMatch) return currencyMatch[1]
  return ''
}

export function buildShareClassInfoByCode<T extends ShareClassFundInput>(funds: T[]) {
  const groups = funds.reduce((acc: Record<string, T[]>, fund) => {
    const name = fundName(fund)
    const baseName = normalizeShareClassBaseName(name)
    const classType = inferShareClass(name)
    if (!baseName || !classType || baseName === name) return acc
    const key = `${baseName}::${fund.type || ''}`
    acc[key] = acc[key] || []
    acc[key].push(fund)
    return acc
  }, {})

  const infoByCode = new Map<string, ShareClassInfo>()
  Object.values(groups)
    .filter((group) => group.length > 1)
    .forEach((group) => {
      group.forEach((fund) => {
        const code = fundCode(fund)
        const name = fundName(fund)
        const baseName = normalizeShareClassBaseName(name)
        const classType = inferShareClass(name)
        const siblings = group
          .filter((item) => fundCode(item) !== code)
          .sort((left, right) => fundCode(left).localeCompare(fundCode(right)))
        const warnings = [
          `同一基金存在 ${group.length} 个份额样本，不能只按收益分独立比较`,
          classType === 'C' ? 'C类通常更依赖销售服务费和持有期，短持/定投前需核总成本' : '',
          classType === 'A' ? 'A类通常需重点核申购费折扣和赎回持有期，长持前需核总成本' : '',
        ].filter(Boolean)

        if (!code) return
        infoByCode.set(code.toUpperCase(), {
          baseName,
          classType,
          siblingCount: group.length,
          siblingCodes: siblings.map((item) => fundCode(item)).filter(Boolean),
          siblingNames: siblings.map((item) => fundName(item)).filter(Boolean),
          hint: `先把 ${group.map((item) => `${inferShareClass(fundName(item)) || '未知'}类 ${fundCode(item)}`).join('、')} 放在同一基金份额框架下比较，再结合持有期、申购费、销售服务费和赎回费判断。`,
          warnings,
        })
      })
    })

  return infoByCode
}

export function summarizeShareClassGroups<T extends ShareClassFundInput>(funds: T[]) {
  const groupKeys = new Set<string>()
  const infoByCode = buildShareClassInfoByCode(funds)
  funds.forEach((fund) => {
    const code = fundCode(fund)
    const info = code ? infoByCode.get(code.toUpperCase()) : null
    if (info) groupKeys.add(`${info.baseName}::${fund.type || ''}`)
  })
  return {
    groupCount: groupKeys.size,
    fundCount: infoByCode.size,
    infoByCode,
  }
}
