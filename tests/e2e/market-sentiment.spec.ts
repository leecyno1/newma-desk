import { expect, test } from '@playwright/test';

const shell = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN || 'http://127.0.0.1:5888';
const historyFixture = () => ({
  days: 20, asOf: '2026-10-15', start: '2026-09-10', current: true, calendarReady: true,
  completed: 20, expected: 20, remaining: 0, commonCount: 5000, missingDates: [], failedDates: [], canContinue: false,
  fetchedDays: 0, source: '验收历史样本', generatedAt: '2026-10-16', note: '固定共同样本，仅用于测试', reason: '',
  summary: { latestUpRatioPct: 75, latestChangePp: 5, mean5Pct: 70, previous5Pct: 50, change5Pp: 20, aboveHalfDays: 12 },
  points: Array.from({ length: 20 }, (_, i) => ({ date: `2026-09-${String(i + 10).padStart(2, '0')}`, status: 'ready',
    reason: '', sampleCount: 5002, excludedCount: 2, upRatioPct: 56 + i, medianPct: 1 })),
});
test.beforeEach(async ({ page }) => {
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment-history', route => route.fulfill({ json: { data: historyFixture() } }));
  await page.route('**/api/mods/market-sentiment/actions/market.limit-boards', route => route.fulfill({ json: { data: boardsFixture() } }));
});
const boardsFixture = () => ({
  current: true, asOf: '2026-10-15', previousDate: '2026-10-14', status: 'ready', reason: '',
  source: '验收涨跌停名单，不含ST', generatedAt: '2026-10-16', receivedAt: '2026-10-16', previousStatus: 'ready', note: '分类互斥，缺失不当零',
  summary: { up: 1, down: 0, broken: 1, attempts: 2, sealRatePct: 50, breakRatePct: 50, knownMaxBoards: 3,
    unknownBoards: 0, reopenedUp: 1, previousUp: 2, retainedUp: 1, retentionRatePct: 50 },
  ladder: [{ boards: 3, count: 1 }],
  tracking: { ready: true, reason: '', note: '未入三池仅为待核验，不能认定断板',
    summary: { total: 2, U: 1, Z: 0, D: 0, absent: 1, mismatches: 0 },
    tiers: [{ boards: 2, total: 1, U: 1, Z: 0, D: 0, absent: 0, retentionRatePct: 100 },
      { boards: null, total: 1, U: 0, Z: 0, D: 0, absent: 1, retentionRatePct: 0 }],
    rows: [{ code: '000001.SZ', name: '验收涨停', industry: '测试', previousBoards: 2, currentBoards: 3, outcome: 'U', progression: 'matched' },
      { code: '000002.SZ', name: '待核验样本', industry: '测试', previousBoards: null, currentBoards: null, outcome: 'absent', progression: 'unknown' }],
    unmatchedContinuations: [],
    quoteVerification: { asOf: '2026-10-15', source: '验收 daily / stk_limit', receivedAt: '2026-10-16', dailyStatus: 'ready', limitsStatus: 'ready', note: '未封涨停不等于下跌',
      summary: { total: 2, priced: 2, returnCount: 2, medianPct: 7.5, belowLimit: 1, atLimit: 1, conflicts: 0, unresolved: 0 },
      rows: [{ code: '000001.SZ', status: 'at_limit', reason: '', close: 11, pct: 10, amountYi: 2, upLimit: 11, downLimit: 9 },
        { code: '000002.SZ', status: 'below_limit', reason: '', close: 10.5, pct: 5, amountYi: 1, upLimit: 11, downLimit: 9 }] } },
  items: [{ code: '000001.SZ', name: '验收涨停', industry: '测试', kind: 'U', boards: 3, openTimes: 4, firstTime: '93027', lastTime: '140000' },
    { code: '600001.SH', name: '验收炸板', industry: '测试', kind: 'Z', boards: null, openTimes: 1, firstTime: '100000', lastTime: null }],
});
const fixture = () => ({
  updated: '2026-10-16T10:00:00+08:00',
  sentiment: { up: 40, down: 40, flat: 20, zt: 4, dt: 1, date: '2026-10-15', source: '验收样本', scope: '测试样本100只' },
  sample: { sampleCount: 103, activeCount: 102, validCount: 100, inactiveCount: 1, missingPctCount: 2, medianPct: 0,
    buckets: [{ label: '下跌', count: 40 }, { label: '平盘', count: 20 }, { label: '上涨', count: 40 }], note: '测试样本，非实际行情' },
  coverage: { received: 103, rejected: 0, invalid: 0, duplicates: 0, conflicts: 0, universeVerified: false },
  session: { expectedDate: '2026-10-15', current: true, calendarStatus: 'ready', usingSaved: false, cached: true },
});

test('市场情绪：含平盘口径、刷新失败清空、缺数与Agent一致', async ({ page }, info) => {
  let mode = 'ready';
  const contexts: any[] = [], errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/market-sentiment/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment', route => {
    if (mode === 'error') return route.fulfill({ status: 503, json: { detail: '验收：数据源暂不可用' } });
    const data = fixture();
    if (mode === 'partial') Object.assign(data.sentiment, { flat: null, zt: null });
    return route.fulfill({ json: { data } });
  });
  await page.goto(`${shell}/?mod=market-sentiment&workspace=sentiment-${Date.now()}`);
  const panel = page.getByLabel('市场情绪研究');
  const root = page.locator('.market-workspace-root');
  await expect(panel).toContainText('40%');
  await expect(panel).toContainText('样本涨跌幅中位数');
  await expect(panel).toContainText('不是封板率');
  await expect(panel.getByLabel('样本涨跌分布')).toContainText('20');
  await expect(root.locator('input')).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.breadth.upRatioPct).toBe(40);
  expect(contexts.at(-1).data.freshness).toBe('fresh');
  expect(contexts.at(-1).data.summary.workspace.sample.inactiveCount).toBe(1);
  expect(contexts.at(-1).data.summary.workspace.sample.missingPctCount).toBe(2);
  expect(contexts.at(-1).selection.symbol).toBeUndefined();
  await expect(panel.locator('.sentiment-evidence-metrics')).toBeInViewport();
  await expect(panel.getByLabel('样本涨跌分布')).toBeInViewport();
  await panel.screenshot({ path: info.outputPath('sentiment-desktop.png') });
  mode = 'error';
  await root.getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel).toContainText('旧数据与旧判断已撤下');
  await expect(panel).not.toContainText('40%');
  await expect(panel).not.toContainText('验收行业');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.status).toBe('error');
  expect(contexts.at(-1).data.summary.workspace.breadth.upRatioPct).toBeNull();
  mode = 'partial';
  await root.getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel).toContainText('证据不完整');
  await expect(panel).not.toContainText('40%');
  await expect(panel).not.toContainText('80%');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.status).toBe('partial');
  mode = 'ready';
  await root.getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel).toContainText('40%');
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  expect(await root.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.getByLabel('样本涨跌分布').scrollIntoViewIfNeeded();
  await expect(panel.getByLabel('样本涨跌分布')).toBeInViewport();
  const panelBox = await panel.boundingBox(), footerBox = await root.locator('.workspace-statusbar').boundingBox();
  expect(footerBox!.y).toBeGreaterThanOrEqual(panelBox!.y + panelBox!.height - 1);
  await panel.screenshot({ path: info.outputPath('sentiment-mobile.png') });
  expect(errors).toEqual([]);
});

test('独立打开市场情绪使用相同口径，不请求个股行情', async ({ page }) => {
  const quoteRequests: string[] = [];
  page.on('request', request => { if (/\/(invoke|actions)\/market.quote/.test(request.url())) quoteRequests.push(request.url()); });
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment', route => route.fulfill({ json: { data: fixture() } }));
  await page.goto(`${shell}/?mod=market-sentiment&workspace=sentiment-standalone-${Date.now()}`);
  const standalone = await page.getByRole('link', { name: '独立打开', exact: true }).getAttribute('href');
  expect(standalone).toContain('standalone=1');
  await page.goto(new URL(standalone!, shell).href);
  const panel = page.getByLabel('市场情绪研究');
  await expect(panel).toContainText('40%');
  await expect(panel).toContainText('样本涨跌幅中位数');
  expect(quoteRequests).toEqual([]);
});

test('市场情绪历史：缺口补齐、固定样本、失败撤下趋势与Agent证据', async ({ page }, info) => {
  let mode = 'partial';
  const contexts: any[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/market-sentiment/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment', route => route.fulfill({ json: { data: fixture() } }));
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment-history', route => {
    if (mode === 'error') return route.fulfill({ status: 503, json: { detail: '历史验收：来源失败' } });
    const data = historyFixture();
    if (mode === 'partial') {
      Object.assign(data, { current: false, completed: 8, remaining: 12, canContinue: true, commonCount: 0,
        missingDates: ['2026-09-11'], reason: '历史存在缺口' });
      Object.assign(data.points[1]!, { status: 'missing', upRatioPct: null, sampleCount: null });
    }
    return route.fulfill({ json: { data } });
  });
  await page.goto(`${shell}/?mod=market-sentiment&workspace=sentiment-history-${Date.now()}`);
  const panel = page.getByLabel('20交易日参与度趋势');
  await expect(panel).toContainText('8 / 20 日就绪');
  await expect(panel.getByRole('img')).toHaveCount(0);
  mode = 'ready';
  await panel.getByRole('button', { name: '补齐下一批历史' }).click();
  await expect(panel.getByRole('img')).toBeVisible();
  await expect(panel).toContainText('20 个百分点');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.history.data?.commonCount).toBe(5000);
  await panel.screenshot({ path: info.outputPath('sentiment-history.png') });
  mode = 'error';
  await page.locator('.market-workspace-root').getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel).toContainText('历史曲线与旧结论已撤下');
  await expect(panel.getByRole('img')).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.history.status).toBe('error');
  expect(contexts.at(-1).data.summary.workspace.history.data).toBeNull();
  await expect(page.getByLabel('市场情绪研究')).toContainText('40%');
});

test('涨跌停名单：分类切换与Agent一致，失败不保留旧名单', async ({ page }, info) => {
  let fail = false, quotesFail = false;
  const contexts: any[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/market-sentiment/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/mods/market-sentiment/actions/market.sentiment', route => route.fulfill({ json: { data: fixture() } }));
  await page.route('**/api/mods/market-sentiment/actions/market.limit-boards', route => {
    if (fail) return route.fulfill({ status: 503, json: { detail: '验收：名单来源失败' } });
    const data = boardsFixture();
    if (quotesFail) Object.assign(data.tracking.quoteVerification, {
      dailyStatus: 'unavailable', limitsStatus: 'unavailable',
      summary: { total: 2, priced: 0, returnCount: 0, medianPct: null, belowLimit: 0, atLimit: 0, conflicts: 0, unresolved: 2 },
      rows: data.tracking.rows.map(row => ({ code: row.code, status: 'unavailable', reason: '同日日线请求失败；不展示旧行情', close: null, pct: null, amountYi: null, upLimit: null, downLimit: null })),
    });
    return route.fulfill({ json: { data } });
  });
  await page.goto(`${shell}/?mod=market-sentiment&workspace=limit-boards-${Date.now()}`);
  const panel = page.getByLabel('涨跌停与连板研究');
  await expect(panel).toContainText('验收涨停');
  await expect(panel).toContainText('09:30:27');
  await panel.getByRole('button', { name: '炸板名单', exact: true }).click();
  await expect(panel).toContainText('验收炸板');
  await expect(panel.locator('tbody')).not.toContainText('验收涨停');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.boards.selectedPool).toBe('Z');
  await panel.getByRole('button', { name: '跌停名单', exact: true }).click();
  await expect(panel).toContainText('该分类为0只');
  await panel.getByRole('button', { name: '昨日涨停去向', exact: true }).click();
  await expect(panel.getByRole('table', { name: '昨日涨停逐股核对' })).toContainText('待核验样本');
  await expect(panel).toContainText('不能认定断板');
  await expect(panel.getByRole('table', { name: '昨日梯队承接' })).toContainText('层级未知');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.boards.selectedPool).toBe('previous');
  expect(contexts.at(-1).data.summary.workspace.boards.data.tracking.summary.absent).toBe(1);
  await expect(panel.getByLabel('同日行情核验')).toContainText('7.5%');
  await expect(panel.getByRole('table', { name: '昨日涨停逐股核对' })).toContainText('有成交 · 未封涨停');
  expect(contexts.at(-1).data.summary.workspace.boards.data.tracking.quoteVerification.summary.belowLimit).toBe(1);
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({ path: info.outputPath('limit-boards.png') });
  quotesFail = true;
  await page.locator('.market-workspace-root').getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel.getByLabel('同日行情核验')).not.toContainText('7.5%');
  await expect(panel.getByRole('table', { name: '昨日涨停逐股核对' })).toContainText('不展示旧行情');
  await expect(panel).toContainText('待核验样本');
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.boards.data?.tracking.quoteVerification.summary.priced).toBe(0);
  fail = true;
  await page.locator('.market-workspace-root').getByRole('button', { name: '刷新', exact: true }).click();
  await expect(panel).toContainText('旧名单与旧判断已撤下');
  await expect(panel.locator('tbody')).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.data.summary.workspace.boards.status).toBe('error');
  expect(contexts.at(-1).data.summary.workspace.boards.data).toBeNull();
  await expect(page.getByLabel('市场情绪研究')).toContainText('40%');
});
