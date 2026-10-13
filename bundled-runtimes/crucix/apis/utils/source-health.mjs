// Shared collection outcomes. A resolved request is not proof that its source returned usable data.
const outcome = (status, reason) => ({ status, reason });
const coverage = (ok, total) => ok === 0
  ? outcome('error', total ? `未取得有效数据（0/${total}）` : '未取得有效数据')
  : ok < total ? outcome('partial', `仅部分数据可用（${ok}/${total}）`) : outcome('ok', '采集完成');

export function sourceOutcome(name, data) {
  if (!data || typeof data !== 'object' || !Object.keys(data).length) return outcome('unknown', '未返回可判定的采集结果');
  if (['no_key', 'no_credentials'].includes(data.status) || /^No .*(?:API key|credentials)/i.test(data.error || '')) {
    return outcome('error', '未配置来源凭据');
  }
  // This collector only describes the WebSocket integration; it does not collect ship positions.
  if (name === 'Maritime') return outcome('unknown', '仅提供接入说明，尚未采集船舶位置');
  if (name === 'YFinance' && Number.isFinite(data.summary?.totalSymbols)) {
    return coverage(Object.values(data.quotes || {}).filter(row => !row.error && Number.isFinite(row.price)).length, data.summary.totalSymbols);
  }
  if (['OpenSky', 'FIRMS'].includes(name) && data.hotspots?.length) {
    const result = coverage(data.hotspots.filter(row => !row.error).length, data.hotspots.length);
    if (result.status !== 'ok') return result;
  }
  if (data.error || ['error', 'unavailable'].includes(data.status) || data.outbreakError) return outcome('error', '来源请求失败或返回错误');
  if (data.stale) return outcome('stale', '使用来源标记的陈旧数据');
  if (data.rwError) return data.hdxDatasets?.length
    ? outcome('partial', 'ReliefWeb 不可用，仅有 HDX 备用数据集，未覆盖原报告') : outcome('error', 'ReliefWeb 与备用来源均无可用数据');
  if (name === 'EIA') return coverage([data.oilPrices?.wti, data.oilPrices?.brent, data.gasPrice, data.inventories?.crudeStocks]
    .filter(row => Number.isFinite(row?.value)).length, 4);
  if (['FRED', 'BLS'].includes(name) && Array.isArray(data.indicators)) return coverage(data.indicators.filter(row => Number.isFinite(row.value)).length, data.indicators.length);
  if (name === 'Safecast' && data.sites?.length) return coverage(data.sites.filter(row => Number.isFinite(row.avgCPM)).length, data.sites.length);
  if (['limited', 'partial'].includes(data.status) || data.partial) return outcome('partial', '来源仅返回部分结果');
  if (data.status === 'no_data') return outcome('unknown', '未取得可用记录，不能据此判定没有事件');
  return outcome('ok', '采集完成');
}

export function sourceHealth(snapshot) {
  const names = new Set([...Object.keys(snapshot.sources || {}), ...Object.keys(snapshot.timing || {}), ...(snapshot.errors || []).map(row => row.name)]);
  const health = [...names].filter(Boolean).map(name => {
    const timing = snapshot.timing?.[name];
    const failed = snapshot.errors?.find(row => row.name === name);
    const result = timing?.reason ? { status: timing.status, reason: timing.reason }
      : snapshot.sources?.[name] ? sourceOutcome(name, snapshot.sources[name])
        : failed || timing?.status === 'error' ? outcome('error', '来源请求失败或超时')
          : outcome('unknown', '缺少来源采集结果');
    return { n: name, ...result, err: result.status !== 'ok', stale: result.status === 'stale' };
  });
  return { health, counts: {
    sourcesQueried: health.length,
    sourcesOk: health.filter(row => row.status === 'ok').length,
    sourcesFailed: health.filter(row => row.status === 'error').length,
    sourcesPartial: health.filter(row => row.status === 'partial').length,
    sourcesStale: health.filter(row => row.status === 'stale').length,
    sourcesUnknown: health.filter(row => row.status === 'unknown').length,
  } };
}
