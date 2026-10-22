// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MacroMonitor } from '@/pages/MacroMonitor';
import { api } from '@/lib/api';

const bridge = vi.hoisted(() => ({ context: undefined as undefined | (() => any) }));
vi.mock('@/lib/vibedesk', () => ({
  createVibeDeskSnapshotCache: () => ({ read: () => null, write: vi.fn() }),
  publishVibeDeskContext: vi.fn(),
  registerVibeDeskContextProvider: (fn: () => any) => { bridge.context = fn; return () => {}; },
  subscribeVibeDeskConfig: () => () => {},
  registerVibeDeskUiActionHandler: () => () => {},
}));
vi.mock('@/lib/api', () => ({ api: { macroMonitor: vi.fn() } }));
vi.mock('@/lib/crucix', () => ({ loadCrucixSnapshot: async () => null }));
afterEach(cleanup);

it('流动性展示统计频率、金额单位和聚合来源，Context保留月末口径', async () => {
  const indicators = [
    { id: 'cn-equity-financing', name: '股票市场融资额', unit: '亿元', value: 627.81,
      previous: 451.29, change: 176.52, direction: 'higher', effect: 'restrictive',
      period: '2026-09', asOf: '2026-09-30', periodEnd: '2026-09-30', frequency: 'month', dateBasis: 'period-end',
      source: { id: 'ths', label: '同花顺聚合 · 股票市场融资', url: 'https://data.10jqka.com.cn/macro/finance/' },
      freshness: { status: 'fresh', ageDays: 22 }, history: [] },
    { id: 'cn-shibor-on', name: 'SHIBOR 隔夜', unit: '%', value: 1.2612,
      previous: 1.261, change: 0.0002, direction: 'higher', effect: 'restrictive',
      period: '2026-10-22', asOf: '2026-10-22', frequency: 'day', dateBasis: 'observation-date',
      source: { id: 'jin10', label: '金十聚合 · SHIBOR', url: 'https://datacenter.jin10.com/reportType/dc_shibor' },
      freshness: { status: 'fresh', ageDays: 0 }, history: [] },
  ];
  vi.mocked(api.macroMonitor).mockResolvedValue({
    generatedAt: '2026-10-22T10:00:00+08:00', indicators: [], events: [], sources: [], gaps: [],
    liquidity: { indicators, groups: [{ id: 'transmission', label: '市场传导', indicators }],
      assessment: { signal: 'mixed', complete: false, observedCount: 1, method: '各自前一有效观测' },
      coverage: { available: 2, total: 9, asOf: '2026-10-22' }, source: '聚合数据',
      note: '月末为统计截止日而非已核验发布日期。' },
  } as never);
  render(<MacroMonitor />);
  await screen.findByText('股票市场融资额');
  expect(screen.getByText(/2026-09 · 已结束月份/)).toBeTruthy();
  expect(screen.getByText(/2026-10-22 · 日度观测/)).toBeTruthy();
  expect(screen.getByText('亿元')).toBeTruthy();
  expect(screen.getByText('较前值 +0.0002 个百分点')).toBeTruthy();
  expect(screen.getByRole('link', { name: '同花顺聚合 · 股票市场融资' }).getAttribute('href')).toBe(indicators[0].source.url);
  expect(screen.getByText('月末为统计截止日而非已核验发布日期。')).toBeTruthy();
  await waitFor(() => expect(bridge.context?.().data.summary.loading).toBe(false));
  expect(bridge.context?.().data.summary.liquidity.indicators[0]).toMatchObject({
    period: '2026-09', periodEnd: '2026-09-30', dateBasis: 'period-end', value: 627.81,
  });
});
