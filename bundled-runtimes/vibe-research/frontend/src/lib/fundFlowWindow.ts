/** The API may return oldest-first (Eastmoney) or newest-first (Sina). */
export function recentFundFlow(rows: readonly { date: string; main_net: number | null }[]) {
  const daily = new Map<string, number | null>();
  for (const row of rows) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(Date.parse(row.date))) continue;
    const value = typeof row.main_net === "number" && Number.isFinite(row.main_net) ? row.main_net : null;
    daily.set(row.date, daily.has(row.date) && daily.get(row.date) !== value ? null : value);
  }
  const sample = [...daily].sort(([a], [b]) => b.localeCompare(a)).slice(0, 20);
  const validCount = sample.filter(([, value]) => value !== null).length;
  return {
    total: sample.length === 20 && validCount === 20 ? sample.reduce((sum, [, value]) => sum + value!, 0) : null,
    records: sample.length,
    validCount,
    start: sample[sample.length - 1]?.[0] ?? null,
    end: sample[0]?.[0] ?? null,
  };
}
