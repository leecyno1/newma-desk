import { describe, expect, it } from 'vitest';
import { recentFundFlow } from '../../bundled-runtimes/vibe-research/frontend/src/lib/fundFlowWindow';

const rows = Array.from({length: 25}, (_, index) => ({date: `2026-08-${String(index + 1).padStart(2, '0')}`, main_net: index + 1}));
describe('company fund flow window', () => {
  it('uses latest dates for both upstream sort orders without mutating input', () => {
    const input = rows.slice().reverse();
    const result = recentFundFlow(input);
    expect(result).toEqual({total: 310, records: 20, validCount: 20, start: '2026-08-06', end: '2026-08-25'});
    expect(recentFundFlow(rows)).toEqual(result);
    expect(input[0].date).toBe('2026-08-25');
  });
  it('does not fill missing values with zero or pull older dates into a window', () => {
    const input = rows.map(row => row.date === '2026-08-25' ? {...row, main_net: null} : row);
    expect(recentFundFlow(input)).toMatchObject({total: null, records: 20, validCount: 19, start: '2026-08-06'});
    expect(recentFundFlow(rows.slice(0, 3))).toMatchObject({total: null, records: 3, validCount: 3});
  });
  it('counts repeated dates once and invalidates conflicting observations', () => {
    expect(recentFundFlow([...rows, rows[24]]).total).toBe(310);
    expect(recentFundFlow([...rows, {...rows[24], main_net: 999}])).toMatchObject({total: null, validCount: 19});
  });
  it('keeps true zero totals and rejects non-finite values', () => {
    expect(recentFundFlow(rows.map(row => ({...row, main_net: 0}))).total).toBe(0);
    expect(recentFundFlow([...rows, {date: '2026-08-26', main_net: NaN}]).total).toBeNull();
  });
});
