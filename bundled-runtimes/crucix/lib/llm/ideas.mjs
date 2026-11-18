// LLM-Powered Trade Ideas — generates actionable ideas from sweep data + delta context
import { FRED_SIGNAL_SERIES, fredSignalObservation } from '../../apis/utils/fred-signals.mjs';
import { currentDeltaSignal, deltaSignalText } from '../delta/format.mjs';
import { COUNT_METRICS, countObservation } from '../delta/count-observations.mjs';
import { blsSignalObservation, blsMonthlyChange, treasuryDebtObservation, METAL_SIGNAL_SERIES,
  metalSignalObservation, metalSessionChange, gscpiSignalObservation, gscpiMonthlyChange } from '../../apis/utils/economic-signals.mjs';
import { ENERGY_SERIES, energySignalObservation, energySpotChange, energyObservationDate } from '../../dashboard/energy.mjs';

/**
 * Generate LLM-enhanced trade ideas from sweep data.
 * @param {LLMProvider} provider - configured LLM provider
 * @param {object} sweepData - synthesized dashboard data
 * @param {object|null} delta - delta from last sweep
 * @param {Array} previousIdeas - ideas from previous runs (for dedup)
 * @returns {Promise<Array>} - array of idea objects
 */
export async function generateLLMIdeas(provider, sweepData, delta, previousIdeas = []) {
  if (!provider?.isConfigured) return null;

  let context;
  try {
    context = compactSweepForLLM(sweepData, delta, previousIdeas);
  } catch (err) {
    console.error('[LLM Ideas] Failed to compact sweep data:', err.message);
    return null;
  }

  const systemPrompt = `You are a quantitative analyst at a macro intelligence firm. You receive structured OSINT + economic data from 25 sources and produce 5-8 actionable trade ideas.

Rules:
- Each idea must cite specific data points from the input
- Collection samples are not incident totals, new events or a safety assessment. Fewer samples never establish lower risk; failed, partial, stale or different-scope collections cannot establish a trend. SDR directory membership does not prove online status.
- Preserve observation dates and units. Unavailable or old observations cannot support current signals; mismatched dates cannot establish a simultaneous divergence.
- Return fewer ideas or abstain with [] when evidence is insufficient; a single yield spread cannot establish normalization or a trend.
- Monthly BLS levels and adjacent-period changes have different units. Observation periods are not release dates; different frequencies do not establish a simultaneous signal. Treasury debt is a USD stock, not a flow, yield or standalone directional trade.
- Energy spot, continuous futures quotes and weekly inventory are different measurements. Preserve their dates, units and sources; continuous futures may roll. OSINT co-occurrence does not establish causality, and price changes alone do not identify supply/demand or future returns.
- Gold/silver are continuous futures quoted in USD per troy ounce, not spot or physical holdings. GSCPI is a monthly standard-deviation index, not percent; its vintage is a source column identifier, not a verified publication timestamp. Do not turn aligned months or NSA price changes into causal inflation forecasts.
- Include entry rationale, risk factors, and time horizon
- Blend geopolitical, economic, and market signals — cross-correlate across domains
- Be specific: name instruments (tickers, futures, ETFs), not vague sectors
- If delta shows significant changes, lead with those
- Do NOT repeat ideas from the "previous ideas" list unless conditions have materially changed
- Rate confidence: HIGH (multiple confirming signals), MEDIUM (thesis supported), LOW (speculative)

Output ONLY valid JSON array. Each object:
{
  "title": "Short title (max 10 words)",
  "type": "LONG|SHORT|HEDGE|WATCH|AVOID",
  "ticker": "Primary instrument",
  "confidence": "HIGH|MEDIUM|LOW",
  "rationale": "2-3 sentence explanation citing specific data",
  "risk": "Key risk factor",
  "horizon": "Intraday|Days|Weeks|Months",
  "signals": ["signal1", "signal2"]
}`;

  try {
    const result = await provider.complete(systemPrompt, context, { maxTokens: 8192, timeout: 90000 });
    const ideas = parseIdeasResponse(result.text);
    if (ideas && ideas.length > 0) {
      return ideas;
    }
    console.warn('[LLM Ideas] No valid ideas parsed from response. Raw length:', result.text?.length, 'First 1000 chars:', JSON.stringify(result.text?.slice(0, 1000)));
    return null;
  } catch (err) {
    console.error('[LLM Ideas] Generation failed:', err.message);
    return null;
  }
}

/**
 * Compact sweep data to ~8KB for token efficiency.
 */
function compactSweepForLLM(data, delta, previousIdeas) {
  const sections = [];

  // Economic indicators
  if (data.fred?.length) {
    const key = data.fred.filter(f => ['VIXCLS', 'DFF', 'DGS10', 'DGS2', 'T10Y2Y', 'BAMLH0A0HYM2', 'DTWEXBGS', 'MORTGAGE30US'].includes(f.id));
    const now = new Date();
    sections.push(`FRED signal policy: daily observations at most 7, weekly mortgage at most 14 calendar days old; local conservative windows, not publication or real-time guarantees. Dates are observation dates, not release dates.`);
    sections.push(`ECONOMIC: ${key.map(f => {
      const valid = fredSignalObservation(f, { now });
      return valid ? `${f.id}=${f.value} ${FRED_SIGNAL_SERIES[f.id].unit} (observation ${f.date})` : `${f.id}=unavailable for current signals`;
    }).join(', ')}`);
  }

  // Energy
  if (data.energy) {
    const now = new Date();
    sections.push('Energy policy: prices/quotes at most 7, weekly inventory at most 14 calendar days old; local conservative windows, not publication or real-time guarantees. Inventory is a stock in thousand barrels, not a flow. Spot history is separate from futures; continuous futures quotes may roll, and their daily closes are not intraday quotes.');
    sections.push(`ENERGY: ${Object.keys(ENERGY_SERIES).map(id => {
      const row = energySignalObservation(data.energy.observations?.find(item => item.id === id), { now });
      if (!row) return `${id}=unavailable for current signals`;
      const change = energySpotChange(row, { now });
      const history = change ? `; dated spot change ${change.change} ${row.unit}${Number.isFinite(change.pctChange) ? ` (${change.pctChange.toFixed(1)}%)` : ' (relative unavailable)'} [${change.fromDate} → ${change.toDate}]` : '; comparable spot change unavailable';
      return `${id}=${row.value} ${row.unit} (${row.kind}, observation ${energyObservationDate(row)}, ${row.source.id}/${row.source.seriesId})${history}`;
    }).join(', ')}`);
  }

  // Metals
  if (data.metals) {
    sections.push(`METALS: ${Object.keys(METAL_SIGNAL_SERIES).map(id => {
      const row = metalSignalObservation(data.metals.observations?.find(item => item.id === id));
      if (!row) return `${id}=unavailable for current signals`;
      const change = metalSessionChange(row);
      return `${id}=${row.value} ${row.unit} (futures, observation ${row.observedAt}, YFinance/${row.source.seriesId}; continuous futures may roll)${change ? `; change vs reported prior close ${change.pct.toFixed(2)}% (basis ${change.basis}; prior-session date not supplied)` : '; reported session change unavailable'}`;
    }).join(', ')}; local conservative age limit 7 calendar days, not a real-time guarantee`);
  }

  // BLS
  if (data.bls?.length) {
    const now = new Date();
    sections.push('BLS monthly policy: last two completed months only, with explicit units and seasonal adjustment; local conservative window, not a release calendar or point-in-time guarantee.');
    sections.push(`BLS_MONTHLY: ${data.bls.map(b => {
      if (!blsSignalObservation(b, { now })) return `${b.id}=unavailable for current signals`;
      const change = blsMonthlyChange(b, { now });
      const mom = change ? `; adjacent change ${change.value} ${change.unit}${change.relative !== null ? ` (${change.relative}%)` : ''} [${change.fromDate} → ${change.toDate}]` : '; adjacent change unavailable';
      return `${b.id}=${b.value} ${b.unit} (observation ${b.date}, ${b.seasonalAdjustment})${mom}`;
    }).join(', ')}`);
  }

  // Treasury
  if (data.treasury != null) {
    const debt = treasuryDebtObservation(data.treasury);
    sections.push(debt ? `TREASURY: totalDebt=${debt.value} USD (observation ${debt.date}; debt coverage=${debt.status}); outstanding stock, not a market yield or a standalone trade signal. Local age limit 7 calendar days, not a publication guarantee.`
      : 'TREASURY: totalDebt=unavailable for current signals (missing, old, unverified or failed debt observation)');
  }

  // Supply chain
  if (data.gscpi) {
    const row = gscpiSignalObservation(data.gscpi);
    const change = gscpiMonthlyChange(data.gscpi);
    sections.push(row ? `SUPPLY_CHAIN: GSCPI=${row.value} ${row.unit} (monthly observation ${row.date}, source GSCPI/NY Fed, vintage column ${row.vintage}); collection ${row.status || 'unknown'}, rejected rows ${row.rejected ?? 'unknown'}, missing vintage cells ${row.missing ?? 'unknown'}; ${change ? `adjacent change ${change.value.toFixed(3)} standard-deviations [${change.fromDate} → ${change.toDate}]` : 'adjacent change unavailable'}; last two completed months only, local conservative window, not a release calendar or point-in-time certification`
      : 'SUPPLY_CHAIN: GSCPI=unavailable for current signals (missing, old or unverified observation)');
  }

  // Geopolitical signals (cap total OSINT text to ~1500 chars to keep prompt compact)
  sections.push('Collection samples are not a safety assessment; reductions never establish lower risk. Regions may overlap, RSS/OSINT displays are capped and WHO/ACLED use explicit query windows. Collection time is not event or publication time.');
  for (const metric of COUNT_METRICS) {
    const sample = countObservation(data, metric.key);
    sections.push(sample ? `SAMPLE ${metric.key}=${sample.value} ${sample.unit}; collection ${sample.asOf}; scope ${JSON.stringify(sample.scope)}`
      : `SAMPLE ${metric.key}=unavailable (missing, partial, stale or unverified; not zero)`);
  }
  const urgentPosts = countObservation(data, 'urgent_posts') ? (data.tg?.urgent || []).slice(0, 5) : [];
  if (urgentPosts.length) {
    const MAX_OSINT_CHARS = 1500;
    let remaining = MAX_OSINT_CHARS;
    const lines = [];
    for (const p of urgentPosts) {
      const text = p.text || '';
      if (remaining <= 0) break;
      const trimmed = text.length > remaining ? text.substring(0, remaining) + '…' : text;
      lines.push(`- ${trimmed}`);
      remaining -= trimmed.length;
    }
    sections.push(`URGENT_OSINT:\n${lines.join('\n')}`);
  }

  // Nuclear
  if (data.nuke?.length) {
    const anomalies = data.nuke.filter(n => n.anom);
    if (anomalies.length) sections.push(`NUCLEAR_ANOMALY: ${anomalies.map(n => `${n.site}: ${n.cpm}cpm`).join(', ')}`);
  }

  // WHO alerts
  if (countObservation(data, 'who_alerts') && data.who?.length) {
    sections.push(`WHO_ALERTS: ${data.who.slice(0, 3).map(w => w.title).join('; ')}`);
  }

  // Defense spending
  if (data.defense?.length) {
    const topContracts = data.defense.slice(0, 3).map(d => `$${((d.amount || 0) / 1e6).toFixed(0)}M to ${d.recipient}`);
    sections.push(`DEFENSE_CONTRACTS: ${topContracts.join(', ')}`);
  }

  // Delta context
  if (delta?.summary) {
    let excluded = 0;
    const now = new Date();
    const groups = Object.fromEntries(['escalated', 'deescalated', 'new'].map(group => [group,
      (delta.signals?.[group] || []).filter(signal => {
        const valid = currentDeltaSignal(signal, data, now);
        if (!valid) excluded++;
        return valid;
      })]));
    const gaps = delta.comparisonGaps?.length || 0;
    sections.push(`\nDELTA_SINCE_LAST_SWEEP: direction=${excluded || gaps ? 'unverified' : delta.summary.direction}, shown=${Object.values(groups).reduce((count, rows) => count + rows.length, 0)}, excluded=${excluded}, comparisonGaps=${gaps}; observation changes, not publication-time surprises`);
    for (const [group, signals] of Object.entries(groups)) {
      if (signals.length) sections.push(`${group === 'new' ? 'NEW_SIGNALS' : group.toUpperCase()}: ${signals.map(deltaSignalText).join('; ')}`);
    }
  }

  // Previous ideas (for dedup)
  if (previousIdeas.length) {
    sections.push(`\nPREVIOUS_IDEAS (avoid repeating):\n${previousIdeas.map(i => `- ${i.title} [${i.type}]`).join('\n')}`);
  }

  return sections.join('\n');
}

/**
 * Parse LLM response into ideas array. Handles markdown code blocks.
 */
function parseIdeasResponse(text) {
  if (!text) return null;

  // Strip markdown code block wrappers (handles trailing whitespace, thinking tags, etc.)
  let cleaned = text.trim();
  // Extract content from code blocks anywhere in the response
  const codeBlockMatch = cleaned.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  if (codeBlockMatch) {
    cleaned = codeBlockMatch[1].trim();
  } else if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```(?:json)?\n?/, '').replace(/\n?```\s*$/, '');
  }
  // Strip any leading/trailing non-JSON text (find the array)
  const arrayMatch = cleaned.match(/(\[[\s\S]*\])/);
  if (arrayMatch) {
    cleaned = arrayMatch[1];
  }

  try {
    const parsed = JSON.parse(cleaned);
    if (!Array.isArray(parsed)) return null;

    // Validate each idea has required fields
    return parsed.filter(idea =>
      idea.title && idea.type && idea.confidence
    ).map(idea => ({
      title: idea.title,
      type: idea.type,
      ticker: idea.ticker || '',
      confidence: idea.confidence,
      rationale: idea.rationale || '',
      risk: idea.risk || '',
      horizon: idea.horizon || '',
      signals: idea.signals || [],
      source: 'llm',
    }));
  } catch {
    // Try to extract JSON array from mixed text
    const match = cleaned.match(/\[[\s\S]*\]/);
    if (match) {
      try {
        const arr = JSON.parse(match[0]);
        return arr.filter(i => i.title && i.type).map(idea => ({
          ...idea,
          source: 'llm',
        }));
      } catch { /* give up */ }
    }
    return null;
  }
}
