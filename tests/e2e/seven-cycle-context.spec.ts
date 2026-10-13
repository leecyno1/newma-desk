import { expect, test } from '@playwright/test'

const shellOrigin = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN

test('周期叠加四个页面向 Desk 提供各自的结构化 Agent 上下文', async ({ page }) => {
  test.skip(!shellOrigin, 'Run against the local Desk stack')
  const contexts: Array<Record<string, any>> = []
  page.on('request', (request) => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/seven-cycle-research/context') {
      contexts.push(request.postDataJSON().context)
    }
  })
  await page.goto(`${shellOrigin}/?mod=seven-cycle-research&workspace=e2e-seven-cycle-${Date.now()}`)
  const frame = page.frameLocator('iframe[title="周期叠加"]')
  await expect.poll(() => contexts.at(-1)?.view?.id).toBe('market-surface')
  await expect.poll(() => contexts.at(-1)?.data?.summary?.contextSource).toBe('structured-page-provider')
  expect(contexts.at(-1)?.filters?.view).toBe('heatmap')
  expect(contexts.at(-1)?.filters?.timeRange).toBe('5y')
  expect(contexts.at(-1)?.filters?.forecastLayer).toBe('history-only')
  await expect(frame.getByRole('button', { name: '同期热图' })).toHaveClass(/active/)
  await expect(frame.getByText('仅历史观测 · 预测请切换曲线或曲面')).toBeVisible()
  await expect(frame.locator('.surface-plot .hm')).toHaveCount(1)
  await expect(frame.locator('.track-rail')).toBeHidden()
  expect(contexts.at(-1)?.data?.summary?.crossSection?.observed).toBeGreaterThan(0)
  expect(contexts.at(-1)?.data?.summary?.crossSection?.observed).toBeLessThanOrEqual(contexts.at(-1)?.data?.summary?.crossSection?.selected)
  await expect(frame.getByRole('region', { name: '同月截面' })).toContainText('缺失不补齐')
  const initialDate = contexts.at(-1)?.selection?.focusedDate
  await frame.locator('.surface-plot .nsewdrag').click()
  await expect.poll(() => contexts.at(-1)?.selection?.focusedDate).not.toBe(initialDate)
  expect(contexts.at(-1)?.selection?.pointLayer).toBe('history')
  expect(contexts.at(-1)?.selection?.comparisonDate).toBe(contexts.at(-1)?.selection?.focusedDate)
  await frame.getByLabel('对比月份').fill('2025-01')
  await expect.poll(() => contexts.at(-1)?.data?.summary?.crossSection?.date).toBe('2025-01')
  await frame.getByRole('button', { name: '2D 轨道' }).click()
  await expect.poll(() => contexts.at(-1)?.filters?.view).toBe('2d')
  await expect.poll(() => contexts.at(-1)?.filters?.forecastLayer).toBe('history-and-forecast')
  await frame.getByRole('button', { name: '同期热图' }).click()
  await expect.poll(() => contexts.at(-1)?.filters?.forecastLayer).toBe('history-only')
  expect(contexts.at(-1)?.data?.freshness).toBe('stale')
  expect(contexts.at(-1)?.data?.freshness).toBe(contexts.at(-1)?.data?.summary?.freshness?.marketData?.status)
  const marketFreshness = contexts.at(-1)?.data?.summary?.freshness?.marketData
  expect(marketFreshness.oldestObservation).toMatch(/^\d{4}-\d{2}$/)
  expect(marketFreshness.newestObservation).toMatch(/^\d{4}-\d{2}$/)
  expect(marketFreshness.oldestObservation <= marketFreshness.newestObservation).toBe(true)
  expect(marketFreshness.staleSelectedTracks).toBeGreaterThan(0)
  expect(contexts.at(-1)?.data?.asOf).toBe(marketFreshness.oldestObservation)
  await expect(frame.getByText(`所选轨道观测 ${marketFreshness.oldestObservation}—${marketFreshness.newestObservation}`, { exact: false })).toBeVisible()
  const vintage = contexts.at(-1)?.data?.summary?.market?.forecastVintage as string
  const today = new Date()
  const expectedForecastLag = Math.max(0, today.getFullYear() * 12 + today.getMonth() + 1 - (Number(vintage.slice(0, 4)) * 12 + Number(vintage.slice(5, 7))))
  expect(contexts.at(-1)?.data?.summary?.freshness?.forecast?.staleMonths).toBe(expectedForecastLag)
  await expect(frame.locator('.snapshot-freshness-note')).toContainText('刷新网页不会更新观测期')
  await expect(frame.getByText(`预测 vintage ${vintage} · 距今 ${expectedForecastLag} 个月`)).toBeVisible()

  await frame.getByRole('link', { name: '七周期研究', exact: true }).click()
  await expect.poll(() => contexts.at(-1)?.view?.id === 'cycles' && contexts.at(-1)?.data?.summary?.contextSource === 'structured-page-provider').toBe(true)
  await frame.getByRole('button', { name: /C1.*康波周期/ }).click()
  await expect.poll(() => contexts.at(-1)?.selection?.cycleId).toBe('C1')
  expect(contexts.at(-1)?.data?.summary?.publication?.forecast).toBe('blocked')

  await frame.getByRole('link', { name: '资产统计', exact: true }).click()
  await expect.poll(() => contexts.at(-1)?.view?.id === 'assets' && contexts.at(-1)?.data?.summary?.contextSource === 'structured-page-provider').toBe(true)
  expect(contexts.at(-1)?.data?.summary?.historicalStatisticsAsOf).toBeTruthy()

  await frame.getByRole('link', { name: '数据与校准', exact: true }).click()
  await expect.poll(() => contexts.at(-1)?.view?.id === 'audit' && contexts.at(-1)?.data?.summary?.contextSource === 'structured-page-provider').toBe(true)
  expect(contexts.at(-1)?.data?.summary?.sources?.length).toBeGreaterThan(0)
  expect(contexts.at(-1)?.data?.summary?.contextSource).toBe('structured-page-provider')
})
