import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const html = readFileSync(process.env.INSTOCK_TEST_SOURCE
  ? join(process.env.INSTOCK_TEST_SOURCE, 'instock/web/templates/rotation.html')
  : new URL('../../bundled-runtimes/instock-analysis/instock/web/templates/rotation.html', import.meta.url), 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));

function page(bridge = {}) {
  const dom = new JSDOM(html, {url: 'http://localhost/mods/rotation', runScripts: 'outside-only'});
  const {window} = dom;
  let readContext;
  let uiAction;
  const charts = new Map();
  window.InStockNewmaDesk = {setContextProvider: fn => {readContext = fn;},
    setUiActionHandler: fn => {uiAction = fn;}, publishContext() {}, ...bridge};
  window.matchMedia = () => ({matches: false});
  window.echarts = {init: element => ({setOption(option) {charts.set(element.id, option);},
    clear() {charts.delete(element.id);}, resize() {}})};
  // Run the real page handlers without starting an external market-data request.
  window.eval(script.replace('    load(false).catch(() => {});', ''));
  return {
    dom,
    charts,
    invokeUi: async (id, input = {}) => uiAction(id, input),
    readContext: () => readContext(),
    edit(id, value) {
      const control = window.document.getElementById(id);
      control.value = value;
      control.dispatchEvent(new window.Event('input', {bubbles: true}));
    },
    render(payload) {
      window.document.dispatchEvent(new window.CustomEvent('instock:history-selected', {
        detail: {record_type: 'experiment', payload, view_source: 'history'},
      }));
    },
    renderSnapshot(payload) {
      window.document.dispatchEvent(new window.CustomEvent('instock:history-selected', {
        detail: {record_type: 'snapshot', payload, view_source: 'history'},
      }));
    },
    text: selector => window.document.querySelector(selector).textContent,
    metrics: () => Array.from(window.document.querySelectorAll('#rotation-experiment-metrics strong'), el => el.textContent),
    context: () => readContext().data.robustnessExperiment,
    fullContext: () => readContext().data,
  };
}

test('UI ranking uses visible parameters and returns the rendered result in standalone mode', async () => {
  const requests = [];
  const payload = {as_of: '2026-10-15', window: 40, summary: {leading_industry: '电力设备'},
    etfs: [], industry_rankings: [], successful_count: 0};
  const p = page({fetchAnalysis: async url => {
    requests.push(url);
    return {ok: true, json: async () => ({ok: true, data: payload})};
  }});
  try {
    p.edit('rotation-window', '40');
    p.edit('rotation-benchmark', '510500');
    p.edit('rotation-as-of', '2026-10-15');
    await assert.rejects(p.invokeUi('analysis.rotation', {benchmark: '510300'}), /隐藏输入/);
    assert.equal(requests.length, 0);
    const result = await p.invokeUi('analysis.rotation');
    const url = new URL(requests[0], 'http://localhost');
    assert.equal(url.pathname, '/api/v1/rotations/snapshots');
    assert.equal(url.searchParams.get('benchmark'), '510500');
    assert.equal(url.searchParams.get('window'), '40');
    assert.equal(url.searchParams.get('asOf'), '2026-10-15');
    assert.equal(url.searchParams.get('refresh'), '1');
    assert.equal(result.asOf, '2026-10-15');
    assert.equal(result.summary.leadingIndustry, '电力设备');
    assert.equal(p.text('#stat-industry'), '电力设备');
    assert.equal(p.readContext().tasks.length, 0);
  } finally {p.dom.window.close();}
});

test('UI experiment follows Desk routing and returns evidence-qualified metrics, not raw optimism', async () => {
  const calls = [];
  let finish;
  const p = page({canInvokeAction: () => true, invokeAction: (id, input) => {
    calls.push({id, input});
    return new Promise(resolve => {finish = resolve;});
  }});
  try {
    p.edit('rotation-rebalance-days', '20');
    p.edit('rotation-cost-bps', '50');
    const pending = p.invokeUi('analysis.rotation.experiment');
    assert.equal(p.readContext().tasks[0].actionId, 'analysis.rotation.experiment');
    assert.equal(p.readContext().actions[1].available, false);
    await assert.rejects(p.invokeUi('analysis.rotation.experiment'), /正在运行/);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].input.rebalanceDays, 20);
    assert.equal(calls[0].input.costBps, 50);
    finish({ok: true, data: {as_of: '2026-10-15', verdict: {state: 'research_ready'},
      summary: {oos_trades: 0, oos_return_pct: 0}}});
    const result = await pending;
    assert.equal(result.verdict, 'legacy_execution_requires_rerun');
    assert.equal(result.outOfSampleReturnPct, null);
    assert.equal(p.context().verdict, result.verdict);
    assert.equal(p.readContext().tasks.length, 0);
    assert.equal(p.readContext().actions[1].available, true);
  } finally {p.dom.window.close();}
});

test('both UI actions reject service failures and preserve visible error state', async () => {
  const p = page({canInvokeAction: () => true,
    invokeAction: async () => ({ok: false, error: {message: '行情服务暂不可用'}})});
  try {
    await assert.rejects(p.invokeUi('analysis.rotation'), /行情服务暂不可用/);
    assert.match(p.text('#rotation-error'), /行情服务暂不可用/);
    await assert.rejects(p.invokeUi('analysis.rotation.experiment'), /行情服务暂不可用/);
    assert.match(p.text('#rotation-experiment-error'), /行情服务暂不可用/);
    assert.equal(p.context(), null);
    assert.equal(p.readContext().tasks.length, 0);
    await assert.rejects(p.invokeUi('unknown'), /不支持/);
  } finally {p.dom.window.close();}
});

test('edited conditions permit a new run while late ranking and workspace results are rejected', async () => {
  const pending = [];
  const bridge = {config: {user: {id: 'u'}, workspace: {id: 'a'}},
    canInvokeAction: () => true, invokeAction: () => new Promise(resolve => pending.push(resolve))};
  const p = page(bridge);
  try {
    const oldRun = p.invokeUi('analysis.rotation');
    await assert.rejects(p.invokeUi('analysis.rotation'), /正在计算/);
    p.edit('rotation-window', '120');
    const newRun = p.invokeUi('analysis.rotation');
    pending[1]({ok: true, data: {as_of: '2026-10-15', summary: {leading_industry: '新结果'}}});
    await newRun;
    pending[0]({ok: true, data: {summary: {leading_industry: '旧结果'}}});
    await assert.rejects(oldRun, /已变化/);
    assert.equal(p.text('#stat-industry'), '新结果');
    const experiment = p.invokeUi('analysis.rotation.experiment');
    bridge.config.workspace.id = 'b';
    p.dom.window.document.dispatchEvent(new p.dom.window.Event('vibedesk:init'));
    pending[2]({ok: true, data: {summary: {oos_trades: 10, oos_return_pct: 25}}});
    await assert.rejects(experiment, /已变化/);
    assert.equal(p.context(), null);
    assert.equal(p.readContext().tasks.length, 0);
  } finally {p.dom.window.close();}
});

test('daily industry breadth scope and selected evidence stay aligned with Agent context', () => {
  const p = page();
  try {
    const evidence = {state: 'available', as_of: '2026-10-21', up_count: 0, down_count: 0,
      flat_count: 5, up_ratio: 0, change_method: 'equal_weight_member_daily_pct'};
    const scope = {source: 'tushare.daily+index_member_all', as_of: '2026-10-21',
      coverage: {industryCount: 31, quoteCount: 5568, listedCount: 5576,
        missingQuoteCount: 8, missingClassificationCount: 0}, point_in_time: false};
    const row = {code: '512800', name: '银行ETF', industry: '银行', rank: 1, total_score: 80,
      proxy_type: 'direct', factor_scores: {}, factor_availability: {}, industry_breadth: evidence};
    p.renderSnapshot({as_of: '2026-10-21', etfs: [row], industry_rankings: [], summary: {},
      price_cutoff: {as_of: '2026-10-21', mode: 'completed_daily_snapshot'},
      industry_breadth: scope, factor_model: {slow_factor_reason: '行业点时慢因子未接入'}});
    assert.match(p.text('#rotation-breadth-source'), /5568\/5576.*缺报价 8/);
    assert.match(p.text('#rotation-breadth-source'), /等权涨跌非指数涨幅.*非历史点时/);
    assert.match(p.text('#rotation-breadth-tag'), /上涨 0\.0%.*2026-10-21/);
    assert.equal(p.fullContext().summary.industryBreadth.coverage.quoteCount, 5568);
    assert.equal(p.fullContext().selectedRotation.industryBreadth.up_ratio, 0);
    assert.equal(p.fullContext().summary.priceCutoff.as_of, '2026-10-21');
    assert.match(p.text('#rotation-meta'), /已完成交易日对齐/);
    p.renderSnapshot({as_of: '2026-10-21', etfs: [{...row,
      industry_breadth: {state: 'unavailable', reason: 'date_mismatch', up_ratio: null}}],
      industry_rankings: [], summary: {}});
    assert.match(p.text('#rotation-breadth-tag'), /日期不匹配/);
    assert.match(p.text('#rotation-breadth-source'), /未取得/);
    assert.equal(p.fullContext().selectedRotation.industryBreadth.up_ratio, null);
    p.renderSnapshot({as_of: '2026-10-21', etfs: [{...row,
      industry_breadth: {state: 'unavailable', reason: 'missing_date', up_ratio: null}}],
      industry_rankings: [], summary: {}});
    assert.match(p.text('#rotation-breadth-tag'), /日期缺失/);
    assert.equal(p.fullContext().selectedRotation.industryBreadth.reason, 'missing_date');
    assert.equal(p.fullContext().selectedRotation.industryBreadth.up_ratio, null);
  } finally {p.dom.window.close();}
});

test('execution evidence keeps theoretical returns distinct and shows directional raw-price checks', () => {
  const p = page();
  try {
    const summary = {state: 'theoretical', planned_legs: 2, price_volume_verified_legs: 2,
      paired_limit_legs: 1, missing_limit_legs: 1, adverse_limit_legs: 0};
    const payload = {verdict: {state: 'research_ready', label: '通过'},
      summary: {oos_trades: 12, oos_return_pct: 3, candidate_state: 'qualified', scorable_variant_count: 5, total_variant_count: 9},
      selected_variant: {out_of_sample: {trades: 12, total_return_pct: 3}},
      execution_audit: {trade_evidence: {train: summary, out_of_sample: summary,
        feeds: [{symbol: '510300', feeds: {price: {source: 'fund_daily', status: 'ready', receivedAt: '2026-10-19'},
          limits: {source: 'etf_limit', status: 'unavailable', usingSaved: true, reason: '请求失败'}}}],
        checks: [{date: '2026-10-19', partition: 'out_of_sample', symbol: '510300', side: 'buy',
          rawOpen: 4.123, lowerLimit: 3.7, upperLimit: 4.5, state: 'checked'}]}}};
    p.render(payload);
    assert.equal(p.metrics()[0], '+3.00%');
    assert.match(p.text('#rotation-verdict-label'), /仅作理论测算/);
    assert.match(p.text('#rotation-experiment-facts'), /仅诊断候选/);
    assert.match(p.text('#rotation-experiment-facts'), /训练可评分 5\/9组/);
    assert.equal(p.context().scorableVariantCount, 5);
    assert.match(p.text('#rotation-trade-evidence'), /缺限价1项/);
    assert.match(p.text('#rotation-trade-sources'), /fund_daily.*etf_limit.*旧缓存未采纳/);
    assert.match(p.text('#rotation-trade-checks'), /510300 买入4.1233.7004.500/);
    assert.equal(p.context().executionEvidenceState, 'theoretical');
    assert.equal(p.context().verdict, 'insufficient_evidence');
    assert.equal(p.context().outOfSampleReturnPct, 3);
    const evidence = payload.execution_audit.trade_evidence;
    evidence.out_of_sample = {...summary, state: 'unresolved', adverse_limit_legs: 1};
    evidence.checks[0] = {...evidence.checks[0], rawOpen: 4.5, state: 'adverse', execution_issue: 'buy_at_upper_limit'};
    payload.selected_variant.out_of_sample.total_return_pct = null;
    payload.summary.oos_return_pct = null;
    p.render(payload);
    assert.equal(p.metrics()[0], '--');
    assert.match(p.text('#rotation-trade-checks'), /涨停买入，不确认成交/);
    assert.equal(p.dom.window.document.querySelectorAll('#rotation-trade-checks tr').length, 1);
    assert.match(p.text('#rotation-verdict-label'), /完整收益不可确认/);
    assert.equal(p.context().outOfSampleReturnPct, null);
    assert.equal(p.context().executionEvidenceState, 'unresolved');
    p.render({verdict: {state: 'research_ready', label: '通过'},
      confirmation_comparison: {verdict: {state: 'improved', label: '确认层同时改善收益与回撤'}},
      parameter_ensemble: {verdict: {state: 'improved', label: '集成改善'}}});
    assert.match(p.text('#rotation-verdict-label'), /旧结果须重跑/);
    assert.match(p.text('#rotation-confirmation-verdict'), /旧确认层结果须重跑/);
    assert.match(p.text('#rotation-ensemble-verdict'), /旧集成结果须重跑/);
    assert.equal(p.context().confirmationVerdict, 'legacy_execution_requires_rerun');
    assert.equal(p.context().verdict, 'legacy_execution_requires_rerun');
    assert.equal(p.text('#rotation-trade-checks'), '');
    assert.equal(p.text('#rotation-trade-sources'), '--');
  } finally {p.dom.window.close();}
});

test('prediction denominators, undefined IC and paired effects agree with Agent context', () => {
  const p = page();
  try {
    const row = {horizon_sessions: 10, samples: 3, missing_samples: 0, effective_non_overlapping_samples: 1,
      rank_ic_mean: null, rank_ic_samples: 0, rank_ic_positive_rate_pct: null,
      spread_samples: 2, top3_minus_bottom3_mean_pct: 0,
      top3_hit_samples: 2, top3_beat_benchmark_rate_pct: 50,
      leader_beat_benchmark_samples: 1, leader_beat_benchmark_rate_pct: 0,
      metric_issue_counts: {constant_returns: 3, top3_boundary_tie: 1}};
    const diagnostics = {statistics_policy: {version: 1}, primary_horizon_sessions: 10,
      out_of_sample: {horizons: [row]}, factor_effectiveness: {factors: [{factor: 'momentum', active: true,
        train: row, out_of_sample: row, state: 'undefined_ic', label: 'IC不可计算',
        leave_one_out: {top3_hit_contribution_oos_pct: 0, paired_samples: {top3_hit_oos: 1}}}]}};
    p.render({prediction_diagnostics: diagnostics});
    assert.match(p.text('#rotation-prediction-rows'), /--（0）/);
    assert.match(p.text('#rotation-prediction-rows'), /50%（2）/);
    assert.match(p.text('#rotation-prediction-rows'), /0%（1）/);
    assert.match(p.text('#rotation-prediction-verdict'), /收益无差异 3次；Top3边界并列 1次/);
    assert.match(p.text('#rotation-factor-effect-rows'), /配对1/);
    assert.equal(p.context().predictionDiagnostics.outOfSampleHorizons[0].rank_ic_mean, null);
    assert.equal(p.context().predictionDiagnostics.factors[0].pairedHitSamples, 1);
    assert.equal(p.context().predictionDiagnostics.factors[0].pairedHitDeltaPercentagePoints, 0);
    assert.equal(p.context().predictionStatisticsState, 'metric_specific_samples');
    p.render({prediction_diagnostics: {...diagnostics, statistics_policy: undefined}});
    assert.match(p.text('#rotation-prediction-verdict'), /旧记录未核验常数截面/);
    assert.equal(p.context().predictionDiagnostics, null);
    assert.equal(p.context().predictionStatisticsState, 'legacy_statistics_requires_rerun');
  } finally {p.dom.window.close();}
});

test('ranking gaps and legacy neutral factor placeholders stay missing in UI and Agent', () => {
  const p = page();
  try {
    const row = {code: '100001', name: '测试ETF', industry: '测试行业', rank: 1, total_score: 80,
      proxy_type: 'direct', factor_scores: {momentum: 80, trend: 80, crowding_reversal: 80,
        valuation: 50, fundamental_quality: 50}, factor_availability: {valuation: false, fundamental_quality: false},
      persistence_score: null, rank_change_5d: null, insight: {evidence: [], risks: []}};
    const payload = {as_of: '2026-10-19', window: 60, etfs: [row], industry_rankings: [],
      factor_model: {active_factors: ['momentum', 'trend']},
      summary: {history_days: 3, history_missing_days: 1, rotation_changes_20d: null, leader_streak_days: 1},
      rotation_history: [{date: '2026-10-15', rankings: [{code: row.code, score: 80}]},
        {date: '2026-10-16', rankings: [], state: 'unavailable'},
        {date: '2026-10-19', rankings: [{code: row.code, score: 85}]}]};
    p.renderSnapshot(payload);
    assert.match(p.text('#rotation-factors'), /估值分位（待数据）--/);
    assert.match(p.text('#rotation-factors'), /基本面质量（待数据）--/);
    assert.doesNotMatch(p.text('#rotation-factors'), /50\.0/);
    assert.match(p.text('#rotation-persistence-tag'), /持续 --/);
    assert.match(p.text('#rotation-history-note'), /缺口 1 日 · 切换 -- 次/);
    assert.match(p.text('#rotation-calendar'), /旧排名未核验独立交易日历/);
    assert.equal(p.fullContext().selectedRotation.factorScores.valuation, null);
    const series = p.charts.get('rotation-history-chart').series[0];
    assert.deepEqual(Array.from(series.data), [80, null, 85]);
    assert.equal(series.connectNulls, false);
    assert.equal(series.smooth, false);
    const calendar = {source: 'test calendar', session_start: '2026-06-01', session_end: '2026-10-19', session_count: 94};
    p.renderSnapshot({...payload, calendar_policy: 'independent_exchange_calendar_exact_dates', calendar,
      etfs: [{...row, factor_scores: {...row.factor_scores, valuation: 0}, factor_availability: {valuation: true}}]});
    assert.match(p.text('#rotation-calendar'), /test calendar/);
    assert.match(p.text('#rotation-factors'), /估值分位（未参与）0\.0/);
    assert.equal(p.fullContext().selectedRotation.factorScores.valuation, 0);
    p.renderSnapshot({...payload, etfs: [{...row, factor_availability: undefined}]});
    assert.match(p.text('#rotation-factors'), /估值分位（待数据）--/);
    assert.equal(p.fullContext().selectedRotation.factorScores.valuation, null);
  } finally {p.dom.window.close();}
});

test('independent calendar provenance is visible and old history is not recertified', () => {
  const p = page();
  try {
    p.render({summary: {}});
    assert.match(p.text('#rotation-experiment-calendar'), /旧记录未使用独立交易日历/);
    assert.equal(p.context().calendarState, 'legacy_calendar_requires_rerun');
    const calendar = {source: 'test calendar', exchange: 'SSE', session_start: '2023-01-02',
      session_end: '2026-10-19', session_count: 800, missing_benchmark_dates: ['2026-10-08'], receivedAt: '2026-10-19'};
    p.render({execution_audit: {calendar_policy: 'independent_exchange_calendar_exact_dates', calendar}});
    assert.match(p.text('#rotation-experiment-calendar'), /test calendar（交易所 SSE）/);
    assert.match(p.text('#rotation-experiment-calendar'), /基准缺整行 1 日/);
    assert.match(p.text('#rotation-experiment-calendar'), /800 个交易日/);
    assert.equal(p.context().calendarState, 'independent_calendar_verified');
    assert.equal(p.context().executionAudit.calendar, calendar);
  } finally {p.dom.window.close();}
});

test('missing experiment evidence is not rendered or sent to Agent as zero', () => {
  const p = page();
  try {
    p.render({as_of: '2026-10-15', summary: {}, selected_variant: {},
      parameter_surface: [{id: 'empty', profile: 'balanced', window: 60}],
      stress_tests: [{cost_bps: 50}], limitations: []});
    assert.deepEqual(p.metrics(), Array(6).fill('--'));
    for (const key of ['coverageYears', 'outOfSampleTrades', 'outOfSampleReturnPct',
      'outOfSampleBenchmarkReturnPct', 'outOfSampleExcessReturnPct', 'outOfSampleMaxDrawdownPct',
      'positiveVariantSharePct', 'confirmationOutOfSampleExcessReturnPct', 'confirmationExcessDeltaPct']) {
      assert.equal(p.context()[key], null, key);
    }
    for (const selector of ['#rotation-stress-list', '#rotation-parameter-rows', '#rotation-prediction-verdict', '#rotation-ensemble-verdict']) {
      assert.doesNotMatch(p.text(selector), /0\.00|NaN|undefined|0\.0%/);
    }
    assert.match(p.text('#rotation-experiment-footnote'), /缺失或无有效样本/);
  } finally {p.dom.window.close();}
});

test('daily risk separates sampled drawdown from period endpoints and reaches Agent context', () => {
  const p = page();
  try {
    const risk = {state: 'complete', max_drawdown_pct: 40, observed_max_drawdown_pct: 40,
      start_date: '2026-01-05', end_date: '2026-01-08',
      current_drawdown_pct: 0, peak_date: '2026-01-05', trough_date: '2026-01-06', recovery_date: '2026-01-07',
      coverage: {observed_closes: 3, expected_closes: 3, observed_periods: 1, expected_periods: 1}, issues: []};
    p.render({selected_variant: {out_of_sample: {trades: 1, max_drawdown_pct: 0}},
      daily_risk: {sampling: 'daily_close_and_execution_open', strategy: risk, benchmark: {...risk, max_drawdown_pct: 0},
        curve: [{date: '2026-01-05', phase: 'initial', strategy_drawdown_pct: 0, benchmark_drawdown_pct: 0},
          {date: '2026-01-06', phase: 'close', strategy_drawdown_pct: 40, benchmark_drawdown_pct: 0}]}});
    assert.match(p.text('#rotation-daily-risk-metrics'), /40\.00 个百分点/);
    assert.match(p.text('#rotation-daily-risk-note'), /峰值 2026-01-05 → 谷底 2026-01-06；恢复于 2026-01-07/);
    assert.match(p.text('#rotation-daily-risk-note'), /2026-01-05 至 2026-01-08，仅含已结束持有期/);
    assert.equal(p.context().dailyRisk.strategy.endDate, '2026-01-08');
    assert.equal(p.context().dailyRisk.strategy.maxDrawdownPct, 40);
    assert.equal(p.context().dailyRisk.curve, undefined);
    const series = p.charts.get('rotation-daily-risk-chart').series[0];
    assert.deepEqual(Array.from(series.data), [-0, -40]);
    assert.equal(series.smooth, false);
    p.render({daily_risk: {strategy: risk, benchmark: {...risk, state: 'incomplete',
      max_drawdown_pct: null, coverage: {observed_closes: 2, expected_closes: 3}}}});
    assert.match(p.text('#rotation-daily-risk-state'), /持仓每日覆盖完整/);
    assert.match(p.text('#rotation-daily-risk-note'), /基准每日行情不完整（收盘 2\/3）/);
    assert.equal(p.context().dailyRisk.strategy.maxDrawdownPct, 40);
    assert.equal(p.context().dailyRisk.benchmark.maxDrawdownPct, null);
  } finally {p.dom.window.close();}
});

test('incomplete daily coverage suppresses full risk claims and preserves chart gaps', () => {
  const p = page();
  try {
    p.render({daily_risk: {strategy: {state: 'incomplete', max_drawdown_pct: 0, current_drawdown_pct: 0,
      observed_max_drawdown_pct: 10, coverage: {observed_closes: 2, expected_closes: 3},
      issues: [{date: '2026-01-06', reason: 'missing_close'}]},
      curve: [{date: '2026-01-06', phase: 'close', strategy_drawdown_pct: null}]}});
    assert.match(p.text('#rotation-daily-risk-state'), /覆盖不完整/);
    assert.match(p.text('#rotation-daily-risk-note'), /下界 10\.00%/);
    assert.match(p.text('#rotation-daily-risk-note'), /2026-01-06 收盘缺价/);
    assert.doesNotMatch(p.text('#rotation-daily-risk-metrics'), /0\.00%/);
    assert.equal(p.context().dailyRisk.strategy.maxDrawdownPct, null);
    assert.equal(p.context().dailyRisk.strategy.currentDrawdownPct, null);
    assert.equal(p.charts.get('rotation-daily-risk-chart').series[0].connectNulls, false);
    assert.equal(p.charts.get('rotation-daily-risk-chart').series[0].data[0], null);
    p.render({summary: {}});
    assert.equal(p.context().dailyRisk, null);
    assert.match(p.text('#rotation-daily-risk-state'), /旧记录无每日路径/);
    assert.equal(p.charts.get('rotation-daily-risk-chart').series[0].data.length, 0);
  } finally {p.dom.window.close();}
});

test('unresolved execution keeps the original decision visible without a zero-return claim', () => {
  const p = page();
  try {
    const audit = {planned_oos_periods: 3, resolved_oos_periods: 2, unresolved_oos_periods: 1,
      equal_weight_missing_periods: 1, prediction_label_coverage: {missing_periods: 2, expected_periods: 9},
      unresolved_decisions: [{signal_date: '2026-01-05', entry_date: '2026-01-06', exit_date: '2026-01-20', symbol: 'A', name: '原选ETF'}]};
    const oos = {trades: 3, resolved_periods: 2, unresolved_periods: 1, execution_state: 'incomplete',
      total_return_pct: null, benchmark_return_pct: null, excess_return_pct: null, max_drawdown_pct: null};
    p.render({execution_audit: audit, selected_variant: {id: 'balanced-w60', out_of_sample: oos},
      parameter_surface: [{id: 'balanced-w60', profile: 'balanced', window: 60, out_of_sample: oos}],
      prediction_diagnostics: {out_of_sample: {horizons: [{horizon_sessions: 20, samples: 7,
        effective_non_overlapping_samples: 2, missing_samples: 2, expected_samples: 9}]}}});
    assert.deepEqual(p.metrics(), Array(6).fill('--'));
    assert.match(p.text('#rotation-execution-audit'), /证据 2\/3 期/);
    assert.match(p.text('#rotation-execution-audit'), /2026-01-05 选择原选ETF/);
    assert.match(p.text('#rotation-parameter-rows'), /3 \/ 缺1期/);
    assert.match(p.text('#rotation-prediction-rows'), /缺信号或标签2/);
    assert.equal(p.context().executionAudit.unresolved_decisions[0].symbol, 'A');
    p.render({summary: {}});
    assert.equal(p.context().executionAudit, null);
    assert.match(p.text('#rotation-execution-audit'), /旧记录未保存时点与成交核验/);
  } finally {p.dom.window.close();}
});

test('scheduled signal gaps are not shown as cash or as an ETF selection', () => {
  const p = page();
  try {
    p.render({execution_audit: {planned_oos_periods: 3, resolved_oos_periods: 1,
      missing_signal_periods: 1, uncertain_holding_periods: 1,
      unresolved_decisions: [{signal_date: '2026-01-05', entry_date: '2026-01-06', exit_date: '2026-01-20',
        symbol: null, name: '持仓待核验', reason: 'insufficient_signal_coverage'}]}});
    assert.match(p.text('#rotation-execution-audit'), /信号不足 1 期/);
    assert.match(p.text('#rotation-execution-audit'), /持仓或成本待定 1 期/);
    assert.match(p.text('#rotation-execution-audit'), /2026-01-05 持仓待核验 · 信号截面不足/);
    assert.doesNotMatch(p.text('#rotation-execution-audit'), /选择持仓待核验|选择null/);
    assert.equal(p.context().executionAudit.missing_signal_periods, 1);
  } finally {p.dom.window.close();}
});

test('observed zero and negative returns remain valid, while empty cohorts have no hit rate', () => {
  const p = page();
  try {
    const observed = {trades: 12, total_return_pct: 0, benchmark_return_pct: 2, excess_return_pct: -2,
      max_drawdown_pct: 0, sharpe: 0, information_ratio: -0.3};
    p.render({engine: {version: '2.5.0'}, as_of: '2026-10-15', selected_variant: {out_of_sample: observed},
      summary: {oos_trades: 12, oos_return_pct: 0, oos_excess_return_pct: -2},
      prediction_diagnostics: {primary_horizon_sessions: 10, out_of_sample: {horizons: [{horizon_sessions: 10,
        samples: 0, effective_non_overlapping_samples: 0, rank_ic_mean: 0, rank_ic_positive_rate_pct: 0,
        top3_beat_benchmark_rate_pct: 0, top3_minus_bottom3_mean_pct: 0, leader_beat_benchmark_rate_pct: 0,
        top3_beat_benchmark_wilson_95_pct: [0, 0]}]}},
      parameter_ensemble: {out_of_sample: {high_confidence: {samples: 0, gross_beat_benchmark_rate_pct: 0,
        gross_beat_benchmark_wilson_95_pct: [0, 0]}}}});
    assert.deepEqual(p.metrics(), ['0.00%', '+2.00%', '-2.00%', '0.00%', '0.00', '-0.30']);
    assert.equal(p.context().outOfSampleReturnPct, 0);
    assert.equal(p.context().outOfSampleExcessReturnPct, -2);
    assert.match(p.text('#rotation-prediction-rows'), /0 完整 \/ Top3不重叠0/);
    assert.doesNotMatch(p.text('#rotation-prediction-rows'), /0\.000|0%/);
    assert.doesNotMatch(p.text('#rotation-ensemble-verdict'), /0\.0%/);
  } finally {p.dom.window.close();}
});

test('old zero-filled empty trade metrics do not become return or drawdown evidence', () => {
  const p = page();
  try {
    p.render({summary: {oos_trades: 0, oos_return_pct: 0, oos_max_drawdown_pct: 0},
      snapshot: {snapshot_id: 'legacy', result: {digest: 'legacy-digest', summary: {oos_return_pct: 0}}},
      selected_variant: {out_of_sample: {trades: 0, total_return_pct: 0, benchmark_return_pct: 0,
        excess_return_pct: 0, max_drawdown_pct: 0, sharpe: 0, information_ratio: 0}}});
    assert.deepEqual(p.metrics(), Array(6).fill('--'));
    assert.equal(p.context().outOfSampleTrades, 0);
    assert.equal(p.context().outOfSampleReturnPct, null);
    assert.equal(p.context().outOfSampleMaxDrawdownPct, null);
    assert.equal(p.context().snapshot.result.summary, undefined);
    assert.equal(p.context().snapshot.result.digest, 'legacy-digest');
  } finally {p.dom.window.close();}
});

test('single samples and ambiguous legacy zero risk ratios are not reported as valid', () => {
  const p = page();
  try {
    const oos = {trades: 1, total_return_pct: 0, max_drawdown_pct: 0, sharpe: 0, information_ratio: 0};
    p.render({engine: {version: '2.5.0'}, selected_variant: {out_of_sample: oos}});
    assert.deepEqual(p.metrics().slice(-2), ['--', '--']);
    p.render({engine: {version: '2.4.0'}, selected_variant: {out_of_sample: {...oos, trades: 12}}});
    assert.deepEqual(p.metrics().slice(-2), ['--', '--']);
  } finally {p.dom.window.close();}
});

test('populated parameter, friction and prediction tables keep measured values', () => {
  const p = page();
  try {
    const oos = {trades: 8, total_return_pct: 4, benchmark_return_pct: 6, excess_return_pct: -2,
      max_drawdown_pct: 19, sharpe: 0.4, information_ratio: -0.2};
    p.render({engine: {version: '2.1.2'}, selected_variant: {id: 'balanced-60', out_of_sample: oos},
      parameter_surface: [{id: 'balanced-60', profile: 'balanced', window: 60, selection_score: 3.5, out_of_sample: oos}],
      stress_tests: [{cost_bps: 50, ...oos}], prediction_diagnostics: {primary_horizon_sessions: 10,
        out_of_sample: {horizons: [{horizon_sessions: 10, samples: 20, effective_non_overlapping_samples: 10,
          rank_ic_mean: -0.123, rank_ic_positive_rate_pct: 0, top3_minus_bottom3_mean_pct: -2,
          top3_beat_benchmark_rate_pct: 60, leader_beat_benchmark_rate_pct: 50,
          non_overlapping_top3_beat_benchmark_rate_range_pct: [0, 80], top3_beat_benchmark_wilson_95_pct: [0, 90]}]}}});
    assert.match(p.text('#rotation-parameter-rows'), /19\.00%/);
    assert.doesNotMatch(p.text('#rotation-parameter-rows'), /--/);
    assert.match(p.text('#rotation-stress-list'), /-2\.00%/);
    assert.match(p.text('#rotation-prediction-rows'), /-0\.1230%/);
    assert.match(p.text('#rotation-prediction-verdict'), /0\.0%–90\.0%/);
    assert.match(p.text('#rotation-experiment-facts'), /历史记录，未重新计算/);
    assert.equal(p.context().engineVersion, '2.1.2');
  } finally {p.dom.window.close();}
});

test('blank, non-finite and nonnumeric statistics are missing, not colored zero', () => {
  const p = page();
  try {
    p.render({selected_variant: {out_of_sample: {trades: 10, total_return_pct: '', benchmark_return_pct: null,
      excess_return_pct: 'unknown', max_drawdown_pct: Infinity, sharpe: NaN, information_ratio: false}}});
    assert.deepEqual(p.metrics(), Array(6).fill('--'));
    assert.equal(p.dom.window.document.querySelectorAll('#rotation-experiment-metrics .up, #rotation-experiment-metrics .down').length, 0);
  } finally {p.dom.window.close();}
});
