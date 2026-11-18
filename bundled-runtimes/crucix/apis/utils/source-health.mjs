// Shared collection outcomes. A resolved request is not proof that its source returned usable data.
const outcome = (status, reason) => ({ status, reason });
const coverage = (ok, total) => ok === 0
  ? outcome('error', total ? `未取得有效数据（0/${total}）` : '未取得有效数据')
  : ok < total ? outcome('partial', `仅部分数据可用（${ok}/${total}）`) : outcome('ok', '采集完成');

// Keep request evidence without copying provider response bodies or credentials.
export function queryReceipt(result, known, partial = false) {
  const code = result?.httpStatus ?? result?.status;
  const httpStatus = Number.isInteger(code) && code >= 400 && code <= 599 ? code : null;
  return {
    status: known ? partial ? 'partial' : 'ok' : 'error',
    reason: known ? partial ? '保留有效记录，覆盖不完整' : '查询完成'
      : httpStatus ? `来源请求失败（HTTP ${httpStatus}）`
        : result?.errorCode === 'REQUEST_TIMEOUT' || /timeout|timed out/i.test(result?.error || '') ? '来源请求超时'
          : '来源请求失败或响应格式无效',
    ...(httpStatus ? { httpStatus } : {}),
    asOf: new Date().toISOString(),
  };
}

export function sourceOutcome(name, data) {
  if (!data || typeof data !== 'object' || !Object.keys(data).length) return outcome('unknown', '未返回可判定的采集结果');
  if (name === 'ReliefWeb' && data.status === 'no_credentials') {
    return outcome('error', '未配置已获批准的 RELIEFWEB_APPNAME；报告与灾害数据未知');
  }
  if (['GDELT', 'Bluesky', 'ReliefWeb'].includes(name) && data.queryStatus && data.coverage
      && ['ok', 'partial', 'error'].includes(data.status)) {
    const rows = Object.values(data.queryStatus);
    const codes = [...new Set(rows.map(row => row.httpStatus).filter(code => Number.isInteger(code) && code >= 400 && code <= 599))];
    return outcome(data.status, `${name} 查询覆盖 ${data.coverage.succeeded}/${data.coverage.requested}`
      + (codes.length ? `；HTTP ${codes.join('/')}` : '')
      + (data.coverage.skipped > 0 ? `；${data.coverage.skipped}项未执行` : '')
      + (rows.some(row => row.reason === '来源请求超时') ? '；来源请求超时' : '')
      + (name === 'ReliefWeb' && data.status !== 'ok' ? '；HDX仅为补充数据集，不计入报告/灾害查询成功数' : ''));
  }
  if (name === 'OFAC') {
    if (!data.coverage || !['ok', 'partial', 'error'].includes(data.status)) {
      return outcome('unknown', '旧 OFAC 快照未证明完整读取名单；制裁风险未知');
    }
    const list = data.sdnList || {};
    return outcome(data.status, (data.status === 'error' ? `OFAC 名单不可用${list.httpStatus ? `（HTTP ${list.httpStatus}）` : ''}`
      : `OFAC SDN 解析 ${list.entryCount ?? '未知'} 条，声明 ${list.recordCount ?? '未知'} 条；${list.reason || '完整性待核验'}`)
      + '；仅 SDN 名单观察，非合规筛查');
  }
  if (name === 'ACLED') {
    if (data.status === 'no_credentials') return outcome('error', '未配置 ACLED 授权账户；冲突事件与死亡人数未知');
    if (data.status === 'error') return outcome('error', `ACLED 查询失败${data.httpStatus ? `（HTTP ${data.httpStatus}）` : ''}；不能认定没有冲突`);
    if (!['ok', 'partial'].includes(data.status) || data.basis !== 'bounded-event-sample' || !data.period?.start || !data.period?.end) return outcome('unknown', '旧冲突快照缺少查询口径，不能认定为零事件');
    return outcome(data.status, `ACLED ${data.period.start} 至 ${data.period.end}：${data.totalEvents} 条已报告样本`
      + (data.coverage?.truncated ? '；达到查询上限，非完整统计' : '')
      + (data.totalFatalities === null ? '；死亡人数不完整' : '') + '；非地区安全结论');
  }
  if (name === 'OpenSanctions') {
    if (data.status === 'no_key') return outcome('error', '未配置 OpenSanctions 授权凭据；制裁风险未知');
    if (!data.coverage || !['ok', 'partial', 'error'].includes(data.status)) {
      return outcome('unknown', '旧制裁快照缺少查询回执；不能认定为零风险');
    }
    const rejected = [...new Set((data.recentSearches || []).map(row => row.httpStatus).filter(Number.isInteger))];
    return outcome(data.status, `制裁关键词查询 ${data.coverage.succeeded}/${data.coverage.requested}`
      + (rejected.length ? `；HTTP ${rejected.join('/')}` : '')
      + (data.metadataStatus !== 'ok' ? '；来源目录不可用或陈旧' : '')
      + '；仅关键词样本，非合规筛查');
  }
  if (['no_key', 'no_credentials'].includes(data.status) || /^No .*(?:API key|credentials)/i.test(data.error || '')) {
    return outcome('error', '未配置来源凭据');
  }
  if (name === 'FRED') {
    if (!data.coverage || !['ok', 'partial', 'error', 'no_data'].includes(data.status)) {
      return outcome('unknown', '旧 FRED 快照缺少逐指标采集回执；覆盖未核验');
    }
    const rejected = [...new Set((data.indicators || []).map(row => row.httpStatus).filter(Number.isInteger))];
    return outcome(data.status === 'no_data' ? 'unknown' : data.status,
      `FRED 指标覆盖 ${data.coverage.succeeded}/${data.coverage.requested}`
      + (rejected.length ? `；HTTP ${rejected.join('/')}` : '')
      + '；日期为观测期，非发布日期或实时保证');
  }
  // This collector only describes the WebSocket integration; it does not collect ship positions.
  if (name === 'Maritime') return outcome('unknown', '仅提供接入说明，尚未采集船舶位置');
  if (name === 'Treasury' && data.coverage) {
    const rows = Object.values(data.coverage);
    const ok = rows.filter(row => row.status === 'ok').length;
    const rejected = rows.filter(row => row.httpStatus).map(row => row.httpStatus);
    const status = rows.every(row => row.status === 'no_data') ? 'unknown'
      : rows.every(row => row.status === 'error') ? 'error' : ok === 2 ? 'ok' : 'partial';
    return outcome(status, `债务/平均付息率覆盖 ${ok}/2${rejected.length ? `；HTTP ${rejected.join('/')}` : ''}；非市场收益率曲线`);
  }
  if (['BLS', 'NOAA'].includes(name) && Number.isInteger(data.httpStatus) && data.httpStatus >= 400 && data.httpStatus <= 599) {
    return outcome('error', `${name} 请求失败（HTTP ${data.httpStatus}）`);
  }
  if (name === 'YFinance' && Number.isFinite(data.summary?.totalSymbols)) {
    const quotes = Object.values(data.quotes || {});
    const result = coverage(quotes.filter(row => !row.error && Number.isFinite(row.price)).length, data.summary.totalSymbols);
    const rejected = [...new Set(quotes.filter(row => row.error && Number.isInteger(row.httpStatus)
      && row.httpStatus >= 400 && row.httpStatus <= 599).map(row => row.httpStatus))];
    return rejected.length ? { ...result, reason: `${result.reason}；行情接口 HTTP ${rejected.join('/')}` } : result;
  }
  if (['OpenSky', 'FIRMS'].includes(name) && data.hotspots?.length) {
    const result = coverage(data.hotspots.filter(row => !row.error).length, data.hotspots.length);
    if (result.status !== 'ok') return result;
  }
  if (name === 'Safecast' && data.sites?.length && data.sites.every(row => row.status)) {
    if (data.sites.every(row => row.status === 'ok')) return outcome('ok', '查询完成；空样本或观测值均不代表辐射安全结论');
    return data.sites.every(row => row.status === 'error') ? outcome('error', '全部辐射区域查询失败')
      : outcome('partial', '辐射数据部分失败、陈旧或格式不完整，安全状态未知');
  }
  if (data.error || ['error', 'unavailable'].includes(data.status) || data.outbreakError) return outcome('error', '来源请求失败或返回错误');
  if (data.stale) return outcome('stale', '使用来源标记的陈旧数据');
  if (data.rwError && !['ok', 'partial', 'error'].includes(data.status)) return data.hdxDatasets?.length
    ? outcome('partial', 'ReliefWeb 不可用，仅有 HDX 备用数据集，未覆盖原报告') : outcome('error', 'ReliefWeb 与备用来源均无可用数据');
  if (name === 'EIA') return coverage([data.oilPrices?.wti, data.oilPrices?.brent, data.gasPrice, data.inventories?.crudeStocks]
    .filter(row => Number.isFinite(row?.value)).length, 4);
  if (name === 'BLS' && Array.isArray(data.indicators)) return coverage(data.indicators.filter(row => Number.isFinite(row.value)).length, data.indicators.length);
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
    const result = ['OpenSanctions', 'ACLED', 'OFAC', 'FRED', 'GSCPI'].includes(name) && snapshot.sources?.[name] ? sourceOutcome(name, snapshot.sources[name])
      : timing?.reason ? { status: timing.status, reason: timing.reason }
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
