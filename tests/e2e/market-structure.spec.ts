import { expect, test } from '@playwright/test';

test('复盘记录：失败保留输入、冻结证据、刷新回看、复核追加和Agent隔离', async ({page}, info) => {
  const contexts: any[] = [], errors: string[] = [];
  let saved: any = null, fail = true, failList = false, ratio = 40;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/instock-market-workbench/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/v1/market-workbench/structure?**', route => {
    const data = fixture(); data.breadth.upRatioPct = ratio;
    return route.fulfill({json: {ok: true, data}});
  });
  await page.route('**/api/v1/rotations/snapshots?**', route => route.fulfill({json: {ok: true, data: continuityFixture()}}));
  await page.route('**/api/v1/market-workbench/reviews**', route => {
    const request = route.request(), detail = /reviews\/[a-f0-9]+$/.test(new URL(request.url()).pathname);
    if (request.method() === 'GET' && !detail && failList) return route.fulfill({status: 503, json: {ok: false, error: {message: '测试跟进清单不可用'}}});
    if (request.method() === 'POST') {
      if (fail) return route.fulfill({status: 503, json: {ok: false, error: {message: '测试写入失败'}}});
      const body = request.postDataJSON();
      if (detail) saved.checks.push({...body, id: 'check1', createdAt: new Date().toISOString()});
      else saved = {schemaVersion: 'newma-desk.market-review.v1', id: 'a'.repeat(32), asOf: '2026-10-15', createdAt: new Date().toISOString(), notes: Object.fromEntries(['judgment', 'support', 'counter', 'watch'].map(key => [key, body[key]])), evidence: body.evidence, captureBasis: '用户保存时的页面证据', checks: []};
    }
    const filter = new URL(request.url()).searchParams.get('status') || 'all';
    const latestCheck = saved?.checks.at(-1) || null, pending = saved && (!latestCheck || latestCheck.outcome === '待观察');
    const item = saved ? {id: saved.id, asOf: saved.asOf, createdAt: saved.createdAt, judgment: saved.notes.judgment, watch: saved.notes.watch,
      status: pending ? 'pending' : 'reviewed', latestCheck, checkCount: saved.checks.length} : null;
    return route.fulfill({json: {ok: true, data: request.method() === 'POST' || detail ? saved : {
      items: item && (filter === 'all' || filter === item.status) ? [item] : [], offset: 0, hasMore: false, status: filter,
      counts: {total: saved ? 1 : 0, pending: pending ? 1 : 0, reviewed: saved && !pending ? 1 : 0},
    }}});
  });
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=journal-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="市场复盘"]');
  const journal = frame.getByRole('region', {name: '我的复盘记录'});
  await expect(frame.getByRole('region', {name: '主线持续性研究'})).toContainText('同池、同口径排名已核对');
  await journal.getByLabel('当前判断', {exact: true}).fill('相对领先不等于普涨 <script>不会执行</script>');
  await journal.getByLabel('支撑证据', {exact: true}).fill('上涨占比40%');
  await journal.getByLabel('次日观察与失效条件', {exact: true}).fill('观察广度能否修复');
  await journal.getByRole('button', {name: '保存本次复盘'}).click();
  await expect(journal).toContainText('测试写入失败');
  await expect(journal.getByLabel('支撑证据', {exact: true})).toHaveValue('上涨占比40%');
  fail = false;
  await journal.getByRole('button', {name: '保存本次复盘'}).click();
  await expect(journal).toContainText('存档回看 · 2026-10-15');
  await expect(frame.getByRole('region', {name: '市场结构研究'})).toBeHidden();
  await expect(frame.locator('.stock-suite-history-fab')).toBeHidden();
  await expect.poll(() => contexts.at(-1)?.data.summary.marketJournal.mode).toBe('archive');
  expect(contexts.at(-1).data.summary.marketStructure).toBeUndefined();
  expect(contexts.at(-1).data.summary.snapshot).toBeUndefined();
  expect(saved.evidence.marketStructure.data.breadth.upRatioPct).toBe(40);
  await journal.getByRole('button', {name: '返回当前'}).click();
  await expect(journal.getByLabel('支撑证据', {exact: true})).toHaveValue('上涨占比40%');
  ratio = 80;
  await page.reload();
  await expect(frame.getByRole('region', {name: '市场结构研究'})).toContainText('80%');
  await journal.getByText('已保存复盘 · 本地长期保留', {exact: true}).click();
  await journal.locator('[data-journal-open]').click();
  await expect(journal.getByRole('table', {name: '冻结证据摘要'})).toContainText('40%');
  await expect(journal.getByRole('table', {name: '冻结证据摘要'})).not.toContainText('80%');
  await journal.getByLabel('复核结论', {exact: true}).selectOption('削弱');
  await journal.getByLabel('实际观察与依据', {exact: true}).fill('观察后广度未改善，不追认原判断');
  await journal.getByRole('button', {name: '追加复核', exact: true}).click();
  await expect(journal).toContainText('复核已追加，原判断未改动');
  await expect(journal.getByRole('region', {name: '后续复核'})).toContainText('观察后广度未改善');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketJournal.record.checks.length).toBe(1);
  expect(contexts.at(-1).data.summary.marketJournal.record.evidence.marketStructure.data.breadth.upRatioPct).toBe(40);
  await journal.screenshot({path: info.outputPath('market-journal-desktop.png')});
  const downloadPromise = page.waitForEvent('download');
  await journal.getByRole('button', {name: '导出完整记录'}).click();
  expect((await downloadPromise).suggestedFilename()).toContain('market-review-2026-10-15');
  await page.setViewportSize({width: 390, height: 850});
  expect(await journal.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await journal.screenshot({path: info.outputPath('market-journal-mobile.png')});
  await page.setViewportSize({width: 1440, height: 1000});
  await journal.getByRole('button', {name: '返回当前'}).click();
  const list = journal.locator('[data-journal-list]');
  await expect(list).toContainText('全部 1 · 待跟进 0 · 已复核 1');
  await expect(list.locator('[data-journal-open]')).toContainText('观察条件：观察广度能否修复');
  await expect(list.locator('[data-journal-open]')).toContainText('观察后广度未改善');
  await journal.getByLabel('跟进筛选').selectOption('pending');
  await expect(list).toContainText('当前没有待跟进记录');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketJournal.followUpQueue.status).toBe('pending');
  expect(contexts.at(-1).data.summary.marketJournal.followUpQueue.items).toEqual([]);
  await journal.getByLabel('跟进筛选').selectOption('reviewed');
  await list.locator('[data-journal-open]').click();
  await expect(journal.locator('.journal-check-target')).toContainText('观察广度能否修复');
  await journal.getByLabel('实际观察与依据', {exact: true}).fill('补充证据不足，继续观察');
  await journal.getByRole('button', {name: '追加复核', exact: true}).click();
  await expect(journal).toContainText('复核已追加，原判断未改动');
  await journal.getByRole('button', {name: '返回当前'}).click();
  await journal.getByLabel('跟进筛选').selectOption('pending');
  await expect(list).toContainText('全部 1 · 待跟进 1 · 已复核 0');
  await expect(list.locator('[data-journal-open]')).toContainText('补充证据不足，继续观察');
  await expect(list.locator('[data-journal-open]')).toContainText('已复核 2 次');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketJournal.followUpQueue.items[0]?.checkCount).toBe(2);
  await list.screenshot({path: info.outputPath('market-followup-desktop.png')});
  await page.setViewportSize({width: 390, height: 1000});
  expect(await list.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await list.screenshot({path: info.outputPath('market-followup-mobile.png')});
  failList = true;
  await list.getByRole('button', {name: '刷新记录'}).click();
  await expect(list).toContainText('测试跟进清单不可用');
  await expect(list.locator('[data-journal-open]')).toHaveCount(0);
  await expect.poll(() => contexts.at(-1)?.data.summary.marketJournal.followUpQueue.error).toBe('测试跟进清单不可用');
  expect(contexts.at(-1).data.summary.marketJournal.followUpQueue.counts).toBeNull();
  failList = false;
  await list.getByRole('button', {name: '刷新记录'}).click();
  await expect(list.locator('[data-journal-open]')).toHaveCount(1);
  expect(errors).toEqual([]);
});

const shell = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN || 'http://127.0.0.1:5888';
const api = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN || 'http://127.0.0.1:8911';
const fixture = () => ({
  schemaVersion: 'newma-desk.market-structure.v1', asOf: '2026-10-15', expectedDate: '2026-10-15', current: true,
  calendar: {status: 'ready'},
  breadth: {current: true, validCount: 100, up: 40, down: 55, flat: 5, upRatioPct: 40, medianPct: -1,
    inactiveCount: 2, missingPctCount: 0, note: '测试样本，不代表全市场', buckets: ['≤−5%', '(−5%,−3%]', '(−3%,0)', '平盘', '(0,3%)', '[3%,5%)', '≥5%'].map((label, index) => ({label, count: [30, 15, 10, 5, 20, 10, 10][index]}))},
  turnover: {current: true, asOf: '2026-10-15', summary: {top20SharePct: 25, sampleTurnoverYi: 1000}},
  indices: ['沪深300', '中证500', '中证1000', '300成长', '300价值'].map((name, index) => ({name, code: ['000300.SH', '000905.SH', '000852.SH', '000918.CSI', '000919.CSI'][index],
    windows: Object.fromEntries([1, 5, 20].map(days => [days, {current: true, returnPct: days + index, baseDate: '2026-09-09', end: '2026-10-15', reason: ''}]))})),
  styles: [{label: '中证1000 − 沪深300', windows: Object.fromEntries([1, 5, 20].map(days => [days, {current: true, spreadPp: 2}]))}],
  relationship: {current: true, text: '沪深300上涨，但样本上涨不足一半'}, notes: ['测试数据；成交额不是净流入'],
});

test('市场结构：窗口、失败降级和Agent一致，窄屏表格内部滚动', async ({ page }, info) => {
  let fail = false;
  const contexts: any[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/instock-market-workbench/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/v1/market-workbench/structure?**', route => fail ? route.fulfill({status: 503}) : route.fulfill({json: {ok: true, data: fixture()}}));
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=market-structure-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="市场复盘"]');
  const panel = frame.getByRole('region', {name: '市场结构研究'});
  await expect(panel).toContainText('沪深300上涨，但样本上涨不足一半');
  await expect(panel.locator('tbody tr')).toHaveCount(5);
  await panel.getByRole('button', {name: '20日', exact: true}).click();
  await expect(panel.locator('tbody tr').first()).toContainText('+20%');
  await expect.poll(() => contexts.at(-1)?.filters.structureDays).toBe(20);
  await expect.poll(() => contexts.at(-1)?.data.summary.marketStructure.data.current).toBe(true);
  await panel.screenshot({path: info.outputPath('market-structure-desktop.png')});
  fail = true;
  await panel.getByRole('button', {name: '刷新结构', exact: true}).click();
  await expect(panel).toContainText('更新失败，保留数据仅供参考');
  await expect(panel).not.toContainText('沪深300上涨，但样本上涨不足一半');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketStructure.data.current).toBe(false);
  const saved = contexts.at(-1).data.summary.marketStructure.data;
  expect(saved.breadth.current).toBe(false);
  expect(saved.relationship.text).toContain('本次更新未确认');
  expect(saved.indices.every((row: any) => Object.values(row.windows).every((window: any) => !window.current))).toBe(true);
  await expect(panel.locator('tbody tr').first()).toContainText('+20%');
  await page.setViewportSize({width: 390, height: 850});
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({path: info.outputPath('market-structure-mobile.png')});
  fail = false;
  await panel.getByRole('button', {name: '刷新结构', exact: true}).click();
  await expect(panel).toContainText('所列窗口已核对');
  await frame.locator('body').evaluate(() => document.dispatchEvent(new CustomEvent('instock:history-selected', {detail: {payload: {
    engine: {name: 'instock-market-workbench'}, snapshot: {}, summary: {}, market_breadth: {}, sector_leaders: [], leaderboards: {},
    as_of: '2020-01-01', data_state: 'partial', data_source: '测试历史',
  }}})));
  await expect(panel).toContainText('该版本未保存市场结构');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketStructure.historical).toBe(true);
  expect(contexts.at(-1).data.summary.marketStructure.data).toBeNull();
});

test('市场结构：独立页初始失败可重试，不依赖榜单成功', async ({ page }) => {
  let fail = true;
  await page.route('**/api/v1/market-workbench/structure?**', route => fail ? route.fulfill({status: 503}) : route.fulfill({json: {ok: true, data: fixture()}}));
  await page.route('**/api/v1/market-workbench/snapshots?**', route => route.fulfill({status: 503}));
  await page.goto('http://127.0.0.1:9988/mods/market-workbench');
  const panel = page.getByRole('region', {name: '市场结构研究'});
  await expect(panel).toContainText('市场结构读取失败');
  fail = false;
  await panel.getByRole('button', {name: '刷新结构'}).click();
  await expect(panel).toContainText('40%');
  await expect(panel.locator('tbody tr')).toHaveCount(5);
});

test('真实市场结构：样本统计、风格差、Desk与Agent一致', async ({ page, request }, info) => {
  const response = await request.get(`${api}/api/capital-flow/market-structure`, {timeout: 60000});
  expect(response.ok()).toBe(true);
  const data = await response.json();
  expect(data.current).toBe(true);
  const breadth = data.breadth;
  expect(breadth.validCount).toBeGreaterThan(4000);
  expect(breadth.up + breadth.down + breadth.flat).toBe(breadth.validCount);
  expect(breadth.buckets.reduce((sum: number, row: any) => sum + row.count, 0)).toBe(breadth.validCount);
  expect(breadth.upRatioPct).toBeCloseTo(breadth.up / breadth.validCount * 100, 8);
  expect(data.styles[0].windows[5].spreadPp).toBeCloseTo(data.indices[2].windows[5].returnPct - data.indices[0].windows[5].returnPct, 8);
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=market-structure-live-${Date.now()}`);
  const panel = page.frameLocator('iframe[title="市场复盘"]').getByRole('region', {name: '市场结构研究'});
  await expect(panel).toContainText(data.asOf);
  await expect(panel).toContainText(`${breadth.upRatioPct.toLocaleString('zh-CN', {maximumFractionDigits: 2})}%`);
  await expect(panel.locator('tbody tr')).toHaveCount(5);
  await panel.screenshot({path: info.outputPath('market-structure-live.png')});
});

const continuityFixture = () => ({
  schemaVersion: 'newma-desk.market-continuity.v1', asOf: '2026-10-15', requestedDate: '2026-10-15',
  current: true, reasons: [], dates: ['2026-09-30', '2026-10-09', '2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15'],
  comparisonDate: '2026-09-30', universeSize: 7,
  summary: {retained: 4, entered: 1, leaderPeriods: 6, leaderChanges: 0},
  rows: Array.from({length: 7}, (_, index) => ({code: `51000${index}`, name: `测试ETF${index}`, industry: `行业${index}`,
    rank: index + 1, ranks: Array(6).fill(index + 1), rankChange: 0, top5Periods: index < 5 ? 6 : 0,
    observedPeriods: 6, phase: index < 5 ? '留在前五' : index === 5 ? '退出前五' : '前五之外',
    signalMode: 'etf_fallback', proxyType: 'direct', proxyNote: '', price20dPct: -2, relative20dPp: 1, current: true})),
  source: '测试回放', notes: ['候选排名不是买卖指令'],
});

test('主线持续性：同日请求、完整候选、失败撤销、历史隔离及Agent同步', async ({page}, info) => {
  let fail = false;
  const contexts: any[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/instock-market-workbench/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/v1/market-workbench/structure?**', route => route.fulfill({json: {ok: true, data: fixture()}}));
  await page.route('**/api/v1/rotations/snapshots?**', route => {
    expect(new URL(route.request().url()).searchParams.get('asOf')).toBe('2026-10-15');
    expect(new URL(route.request().url()).searchParams.get('view')).toBe('continuity');
    return fail ? route.fulfill({status: 503}) : route.fulfill({json: {ok: true, data: continuityFixture()}});
  });
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=continuity-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="市场复盘"]');
  const panel = frame.getByRole('region', {name: '主线持续性研究'});
  await expect(panel).toContainText('同池、同口径排名已核对');
  await expect(panel.locator('tbody tr')).toHaveCount(6);
  await expect(panel).toContainText('-2.00%');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketContinuity.data.current).toBe(true);
  await panel.getByRole('button', {name: '查看全部候选'}).click();
  await expect(panel.locator('tbody tr')).toHaveCount(7);
  await expect.poll(() => contexts.at(-1)?.filters.continuityShowAll).toBe(true);
  fail = true;
  await panel.getByRole('button', {name: '刷新主线'}).click();
  await expect(panel).toContainText('主线证据读取失败');
  await expect(panel).not.toContainText('留在前五');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketContinuity.data.current).toBe(false);
  expect(contexts.at(-1).data.summary.marketContinuity.data.summary.retained).toBeNull();
  await page.setViewportSize({width: 390, height: 850});
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({path: info.outputPath('market-continuity-mobile.png')});
  fail = false;
  await panel.getByRole('button', {name: '刷新主线'}).click();
  await expect(panel).toContainText('同池、同口径排名已核对');
  await frame.locator('body').evaluate(() => document.dispatchEvent(new CustomEvent('instock:history-selected', {detail: {payload: {
    engine: {name: 'instock-market-workbench'}, snapshot: {}, summary: {}, market_breadth: {}, sector_leaders: [], leaderboards: {},
    as_of: '2020-01-01', data_state: 'partial', data_source: '测试历史',
  }}})));
  await expect(panel).toContainText('历史记录未保存持续性证据');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketContinuity.historical).toBe(true);
  expect(contexts.at(-1).data.summary.marketContinuity.data).toBeNull();
  expect(errors).toEqual([]);
});

test('真实主线持续性：复用轮动并对齐已结束交易日', async ({page, request}, info) => {
  test.setTimeout(150_000);
  const undated = await request.get('http://127.0.0.1:9988/api/v1/rotations/snapshots?view=continuity');
  expect(undated.status()).toBe(400);
  const structure = await (await request.get(`${api}/api/capital-flow/market-structure`, {timeout: 60000})).json();
  const response = await request.get(`http://127.0.0.1:9988/api/v1/rotations/snapshots?window=60&benchmark=510300&asOf=${structure.expectedDate}&view=continuity`, {timeout: 100000});
  expect(response.ok()).toBe(true);
  const payload = await response.json(), data = payload.data;
  expect(data.schemaVersion).toBe('newma-desk.market-continuity.v1');
  expect(data.asOf).toBe(structure.expectedDate);
  expect(data.rows.length).toBeGreaterThan(5);
  expect(data.dates.length).toBe(20);
  if (data.current) {
    expect(data.summary.retained + data.summary.entered).toBe(5);
    expect(data.rows.every((row: any) => row.top5Periods <= row.observedPeriods)).toBe(true);
  } else expect(data.reasons.length).toBeGreaterThan(0);
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=continuity-live-${Date.now()}`);
  const panel = page.frameLocator('iframe[title="市场复盘"]').getByRole('region', {name: '主线持续性研究'});
  await expect(panel).toContainText(data.asOf, {timeout: 90000});
  await expect(panel.locator('tbody tr').first()).toContainText(data.rows[0].industry);
  await panel.screenshot({path: info.outputPath('market-continuity-live.png')});
  await panel.getByRole('button', {name: `核对${data.rows[0].industry}证据`, exact: true}).click();
  const evidence = page.frameLocator('iframe[title="市场复盘"]').getByRole('region', {name: '主线交叉证据'});
  await expect(evidence).toContainText('ETF 申赎估算', {timeout: 70000});
  await expect(evidence).toContainText('窗口已核对');
  await expect(evidence).toContainText(data.rows[0].code);
  await expect(evidence).toContainText(structure.expectedDate);
  await evidence.screenshot({path: info.outputPath('market-evidence-live.png')});
});

const evidenceFixture = (code = '510000') => ({
  schemaVersion: 'newma-desk.market-evidence.v1', code: `${code}.SH`, industry: '行业0', requestedDate: '2026-10-15',
  catalog: {item: {name: '目录银行ETF', indexName: '中证银行', indexCode: '399986.SZ'}, status: 'ready', usingSaved: false, receivedAt: '2026-10-16'},
  mapping: {configuredName: '测试ETF', proxyType: 'direct', proxyNote: '', basis: '显式配置'},
  etf: {source: '测试份额净值', asOf: '2026-10-15', note: '不是外部新增现金', sourceNote: '', current: true,
    windows: Object.fromEntries([1, 5, 20].map(day => [day, {baseDate: '2026-09-15', end: '2026-10-15', flowYi: .12, strengthPct: 1.2, current: true, reason: ''}]))},
  policies: {start: '2026-07-18', end: '2026-10-15', matchedCount: 1, pointInTimeVerified: false, note: '规则命中不证明受益方向', items: [{
    title: '测试监管政策', sourceUrl: 'https://www.gov.cn/test-policy', institution: '测试机关', publishedDate: '2026-10-14',
    dateBasis: '政策记录日期，原文发布日期待核验', matchedEntities: [{displayName: '银行', evidence: '商业银行'}],
    timingLabel: '复盘日后入库，仅供事后参考', firstSeenAt: '2026-10-16', documentStatus: 'missing', pointInTimeVerified: false,
  }]}, notes: ['历史可知时点未验证'],
});

test('交叉证据：选中对象、原文与入库时间、失败不串数据、上下文和历史隔离', async ({page}, info) => {
  let fail = false;
  const contexts: any[] = [];
  page.on('request', request => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname === '/api/mods/instock-market-workbench/context') contexts.push(request.postDataJSON().context);
  });
  await page.route('**/api/v1/market-workbench/structure?**', route => route.fulfill({json: {ok: true, data: fixture()}}));
  await page.route('**/api/v1/rotations/snapshots?**', route => route.fulfill({json: {ok: true, data: continuityFixture()}}));
  await page.route('**/api/v1/market-workbench/evidence?**', route => {
    const query = new URL(route.request().url()).searchParams;
    expect(query.get('asOf')).toBe('2026-10-15');
    return fail ? route.fulfill({status: 503}) : route.fulfill({json: {ok: true, data: evidenceFixture(query.get('code')!)}});
  });
  await page.goto(`${shell}/?mod=instock-market-workbench&workspace=market-evidence-${Date.now()}`);
  const frame = page.frameLocator('iframe[title="市场复盘"]');
  const continuity = frame.getByRole('region', {name: '主线持续性研究'});
  const panel = frame.getByRole('region', {name: '主线交叉证据'});
  await expect(panel).toContainText('点击上方行业名称');
  await continuity.getByRole('button', {name: '核对行业0证据', exact: true}).click();
  await expect(panel).toContainText('中证银行');
  await expect(panel).toContainText('复盘日后入库，仅供事后参考');
  await expect(panel.getByRole('link', {name: '测试监管政策'})).toHaveAttribute('href', 'https://www.gov.cn/test-policy');
  await expect(panel.locator('tbody tr')).toHaveCount(3);
  await expect.poll(() => contexts.at(-1)?.data.summary.marketEvidence.data.code).toBe('510000.SH');
  expect(contexts.at(-1).data.summary.marketEvidence.data.policies.pointInTimeVerified).toBe(false);
  fail = true;
  await continuity.getByRole('button', {name: '核对行业1证据', exact: true}).click();
  await expect(panel).toContainText('交叉证据读取失败');
  await expect(panel).not.toContainText('目录银行ETF');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketEvidence.selected.code).toBe('510001');
  expect(contexts.at(-1).data.summary.marketEvidence.data).toBeNull();
  fail = false;
  await panel.getByRole('button', {name: '重查证据'}).click();
  await expect(panel).toContainText('510001.SH');
  await page.setViewportSize({width: 390, height: 850});
  expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await panel.screenshot({path: info.outputPath('market-evidence-mobile.png')});
  await continuity.getByRole('button', {name: '刷新主线'}).click();
  await expect(panel).toContainText('点击上方行业名称');
  await expect.poll(() => contexts.at(-1)?.data.summary.marketEvidence.selected).toBeNull();
});
