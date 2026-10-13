// Keep the selected value and its provenance together. Yahoo futures are not EIA spot prices.
export function energySnapshot(eia = {}, quotes = {}) {
  const definitions = [
    ['wti', 'WTI', eia.oilPrices?.wti, 'RWTC', 'CL=F', '美元/桶', 'daily'],
    ['brent', 'Brent', eia.oilPrices?.brent, 'RBRTE', 'BZ=F', '美元/桶', 'daily'],
    ['naturalGas', 'Henry Hub 天然气', eia.gasPrice, 'RNGWHHD', 'NG=F', '美元/百万英热单位', 'daily'],
    ['crudeStocks', '美国商业原油库存（不含战略储备）', eia.inventories?.crudeStocks, 'WCESTUS1', null, '千桶', 'weekly'],
  ];
  const observations = definitions.map(([id, label, row, seriesId, symbol, unit, frequency]) => {
    const quote = symbol ? quotes[symbol] : null;
    if (quote && Number.isFinite(quote.price)) {
      return {
        id, label: `${label}期货`, value: quote.price, kind: 'futures', frequency: 'quote',
        unit: quote.currency === 'USD' ? unit : null,
        period: null, observedAt: quote.observedAt || null,
        source: { id: 'YFinance', label: 'Yahoo Finance', seriesId: symbol,
          url: `https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/` },
        note: '期货公开报价，可能延迟；不能当作 EIA 现货价，历史连续报价可能换月。',
      };
    }
    const available = Number.isFinite(row?.value);
    return {
      id, label: symbol ? `${label}现货` : label, value: available ? row.value : null,
      kind: symbol ? 'spot' : 'inventory', frequency, unit,
      period: available ? row.period || null : null, observedAt: null,
      source: row?.source || { id: 'EIA', label: '美国能源信息署 EIA', seriesId,
        url: `https://www.eia.gov/dnav/${id === 'naturalGas' ? 'ng' : 'pet'}/hist/LeafHandler.ashx?n=${id === 'naturalGas' ? 'NG' : 'PET'}&s=${seriesId}&f=${frequency === 'weekly' ? 'W' : 'D'}` },
      note: available ? row.note || '保留来源统计期；不是采集时间或已核实的发布日期。'
        : eia.gaps?.[id] || '来源未返回数据，不以零值代替。',
    };
  });
  const values = Object.fromEntries(observations.map(item => [item.id, item.value]));
  const futureHistory = quotes['CL=F']?.history;
  return {
    // Preserve the upstream dashboard's scalar API; Desk consumes observations.
    wti: values.wti, brent: values.brent, natgas: values.naturalGas, crudeStocks: values.crudeStocks,
    wtiRecent: observations[0].kind === 'futures'
      ? (futureHistory || []).map(point => point.close)
      : (eia.oilPrices?.wti?.recent || []).map(point => point.value),
    observations, signals: eia.signals || [],
  };
}
