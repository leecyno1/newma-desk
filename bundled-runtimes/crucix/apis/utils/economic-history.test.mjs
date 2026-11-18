import assert from 'node:assert/strict';
import test from 'node:test';
import { synthesize } from '../../dashboard/inject.mjs';

test('synthesis keeps dated energy and supply chain history on the selected source', async () => {
  const recent = [{ period: '2026-10-27', value: 103.37 }, { period: '2026-10-26', value: 105.25 }];
  const history = [{ date: '2026-09', value: 1.28 }, { date: '2026-08', value: 1.2 }];
  const raw = { sources: {
    EIA: { oilPrices: { wti: { value: 103.37, period: '2026-10-27', recent } } },
    GSCPI: { latest: { date: '2026-09', value: 1.28 }, history },
  } };
  const spot = await synthesize(raw, { refreshNews: false });
  assert.deepEqual(spot.energy.observations[0].history, recent);
  assert.deepEqual(spot.gscpi.history, history);
  const futures = await synthesize({ sources: { ...raw.sources,
    YFinance: { quotes: { 'CL=F': { price: 104, currency: 'USD', history: [{ date: '2026-10-26', close: 106 }] } } },
  } }, { refreshNews: false });
  assert.equal(futures.energy.observations[0].kind, 'futures');
  assert.deepEqual(futures.energy.observations[0].history, []); // Never borrow EIA spot history for a futures quote.
});
