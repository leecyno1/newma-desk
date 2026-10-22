import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const html = readFileSync(new URL('../../bundled-runtimes/instock-analysis/instock/web/templates/strategy_validation.html', import.meta.url), 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));

function page(bridge = {}) {
  const dom = new JSDOM(html, {url: 'http://localhost/mods/strategy-validation', runScripts: 'outside-only'});
  const {window} = dom;
  let context, uiAction;
  const charts = new Map();
  window.InStockNewmaDesk = {setContextProvider: fn => {context = fn;}, setUiActionHandler: fn => {uiAction = fn;}, publishContext() {}, ...bridge};
  window.echarts = {init: element => ({setOption(option) {charts.set(element.id, option);}, clear() {charts.delete(element.id);}, resize() {}})};
  window.eval(script);
  return {dom, charts, context: () => context().data, invokeUi: (input = {}) => uiAction('analysis.strategy-validation', input), field: name => window.document.getElementById('validation-' + name),
    text: id => window.document.getElementById(id).textContent,
    render(metrics, version = '1.2.0', extra = {}) {
      window.document.dispatchEvent(new window.CustomEvent('instock:history-selected', {detail: {payload: {
        engine: {name: 'instock-strategy-validation', version}, out_of_sample: version === '1.2.0' ? {portfolio_state: 'complete', ...metrics} : metrics,
        ...(version === '1.2.0' ? {validation_audit: {split_decision_date: '2026-01-08', train_signals: 1, out_of_sample_signals: 2, purged_decision_dates: ['2026-01-06']}} : {}),
        coverage: {executed_signals: metrics.trades, input_signals: 2},
        snapshot: {snapshot_id: 'fixture', result: {digest: 'fixture-digest', summary: {out_of_sample: metrics}}}, limitations: [], trades: [], ...extra,
      }, view_source: 'history'}}));
    }};
}

test('empty and legacy zero-filled validation evidence stays null in UI and Agent', () => {
  const p = page();
  try {
    for (const value of [null, 0]) {
      p.render({trades: 0, total_return_pct: value, max_drawdown_pct: value, excess_return_pct: value,
        sharpe: value, information_ratio: value}, '1.0.1');
      for (const field of ['return', 'drawdown', 'excess']) assert.equal(p.text('validation-' + field), '--');
      assert.equal(p.context().outOfSample.total_return_pct, null);
      assert.equal(p.context().outOfSample.sharpe, null);
      assert.equal(p.context().snapshot.result.summary, undefined);
      assert.equal(p.context().snapshot.result.digest, 'fixture-digest');
      assert.equal(p.context().snapshot.snapshot_id, 'fixture');
      assert.match(p.text('validation-status'), /旧记录未核验完整日历/);
    }
  } finally {p.dom.window.close();}
});

test('overlap suppresses portfolio claims but keeps labeled signal diagnostics and full ledger', () => {
  const p = page();
  try {
    p.render({trades: 2, portfolio_state: 'overlapping', total_return_pct: 999,
      max_drawdown_pct: 0, overlap_decision_dates: ['2026-01-12'],
      signal_diagnostics: {samples: 2, expected_samples: 2, mean_return_pct: 3, mean_excess_pct: -1, win_rate_pct: 50, beat_benchmark_rate_pct: 0}}, '1.2.0', {
        trades: [{decision_date: '2026-01-06', entry_date: '2026-01-07', exit_date: '2026-01-09', symbols: ['000001'], partition: 'purged', execution_state: 'resolved', net_return_pct: 1, benchmark_return_pct: 2},
          {decision_date: '2026-01-12', entry_date: '2026-01-13', exit_date: null, symbols: ['000002'], partition: 'out_of_sample', execution_state: 'unresolved', reason: 'holding_window_incomplete', net_return_pct: null, benchmark_return_pct: null}],
      });
    assert.equal(p.text('validation-return'), '--');
    assert.equal(p.text('validation-drawdown'), '--');
    assert.equal(p.text('validation-signal-return'), '3.00%');
    assert.equal(p.text('validation-signal-beat'), '0.00%');
    assert.match(p.text('validation-status'), /持有期存在重叠/);
    assert.match(p.text('validation-trades'), /跨界剔除/);
    assert.match(p.text('validation-trades'), /持有期尚不完整/);
    assert.equal(p.context().outOfSample.total_return_pct, null);
    assert.equal(p.context().validationAudit.split_decision_date, '2026-01-08');
    assert.equal(p.context().unresolvedSignals.length, 1);
  } finally {p.dom.window.close();}
});

test('incomplete segment cannot present partial compounded results as full performance', () => {
  const p = page();
  try {
    p.render({trades: 1, portfolio_state: 'incomplete', unresolved_signals: 1, total_return_pct: 8, max_drawdown_pct: 0});
    assert.equal(p.text('validation-return'), '--');
    assert.equal(p.text('validation-drawdown'), '--');
    assert.match(p.text('validation-status'), /1 笔未核验/);
  } finally {p.dom.window.close();}
});

test('observed zeros and losses survive normalization; one observation has no ratio', () => {
  const p = page();
  try {
    p.render({trades: 1, total_return_pct: 0, max_drawdown_pct: 0, excess_return_pct: -2, sharpe: 0});
    assert.equal(p.text('validation-return'), '0.00%');
    assert.equal(p.text('validation-drawdown'), '0.00%');
    assert.equal(p.text('validation-excess'), '-2.00%');
    assert.equal(p.context().outOfSample.sharpe, null);
    p.render({trades: 2, total_return_pct: 0, sharpe: 0, information_ratio: 0});
    assert.equal(p.context().outOfSample.sharpe, 0);
    p.render({trades: 2, total_return_pct: 0, sharpe: 0, information_ratio: 0}, '1.0.1');
    assert.equal(p.context().outOfSample.sharpe, null);
    assert.equal(p.context().outOfSample.information_ratio, null);
  } finally {p.dom.window.close();}
});

const input = () => ({schema_version: 'instock-strategy-validation-packet-v1',
  strategy: {id: 'frozen-original', name: '历史样例', source_module: 'rotation'},
  as_of: '2026-06-30', benchmark: '510300', holding_period_sessions: 2, cost_bps_per_side: 0,
  signals: [{decision_date: '2026-06-01', symbols: ['000001']}, {decision_date: '2026-06-08', symbols: ['000002']}]});
const output = packet => ({engine: {name: 'instock-strategy-validation', version: '1.2.1'}, input_packet: packet,
  strategy: packet.strategy, as_of: packet.as_of, benchmark: packet.benchmark,
  out_of_sample: {portfolio_state: 'complete', trades: 1, total_return_pct: 3},
  coverage: {executed_signals: 2, input_signals: 2}, validation_audit: {split_decision_date: '2026-06-08'},
  snapshot: {snapshot_id: 'run'}, limitations: [], trades: []});
const flush = () => new Promise(resolve => setImmediate(resolve));
function changed(p, name, value) { p.field(name).value = value; p.field(name).dispatchEvent(new p.dom.window.Event('input', {bubbles: true})); }
function restore(p) { p.render({trades: 1, total_return_pct: 3}, '1.2.1', output(input())); }

test('host validation uses the visible complete ledger and returns only after rendering', async () => {
  let submitted, resolve;
  const p = page({canInvokeAction: () => true, invokeAction: (_, value) => {
    submitted = value; return new Promise(done => {resolve = done;});
  }});
  try {
    await assert.rejects(p.invokeUi(), /至少加入 2 条历史决策/);
    assert.equal(submitted, undefined);
    restore(p);
    assert.throws(() => p.invokeUi({signals: []}), /不接受隐藏输入/);
    const pending = p.invokeUi();
    assert.equal(p.context().state, 'running');
    await assert.rejects(p.invokeUi(), /正在运行/);
    assert.equal(submitted.strategy.id, 'frozen-original');
    assert.equal(submitted.signals.length, 2);
    assert.equal(submitted.cost_bps_per_side, 0);
    resolve({ok: true, data: output(submitted)});
    const result = await pending;
    assert.equal(result.resultSource, 'current');
    assert.equal(result.snapshot.snapshot_id, p.context().snapshot.snapshot_id);
    assert.equal(p.field('run').disabled, false);
  } finally {p.dom.window.close();}
});

test('host receives validation failure and stale-result rejection without reverting edits', async () => {
  const requests = [];
  const p = page({canInvokeAction: () => true, invokeAction: () => new Promise((resolve, reject) => requests.push({resolve, reject}))});
  try {
    restore(p);
    const pending = p.invokeUi(); changed(p, 'name', '新的草稿');
    requests[0].resolve(output(input()));
    await assert.rejects(pending, /草稿或工作区已变化/);
    assert.equal(p.context().state, 'draft');
    assert.equal(p.context().draft.strategy.name, '新的草稿');
    const failed = p.invokeUi(); requests[1].reject(new Error('验证数据源断开'));
    await assert.rejects(failed, /验证数据源断开/);
    assert.equal(p.context().state, 'error');
    assert.match(p.text('validation-alert'), /验证数据源断开/);
    assert.equal(p.field('run').disabled, false);
  } finally {p.dom.window.close();}
});

test('explicit sleeves render independent capital path, retain gaps and restore allocation input', async () => {
  let submitted;
  const packet = {...input(), capital_model: {mode: 'fixed_sleeves', slots: 2}};
  const book = {state: 'incomplete', benchmark_state: 'complete', total_return_pct: 0, max_drawdown_pct: null,
    excess_return_pct: -2, ending_cash: 1, planned_signals: 3, allocated_signals: 2,
    skipped_signals: 1, unresolved_signals: 0, pending_signals: 0, open_sleeves: 0,
    cost_pct_initial_capital: 0, coverage: {expected_marks: 9, observed_marks: 8},
    curve: [{date: '2026-06-02', phase: 'close', nav: 1, cash: 0, benchmark_nav: 1},
      {date: '2026-06-03', phase: 'close', nav: null, cash: 0, benchmark_nav: 1.01},
      {date: '2026-06-04', phase: 'close', nav: 1, cash: 1, benchmark_nav: 1.02}],
    ledger: [{decision_date: '2026-06-03', symbols: ['000001'], slot: null, state: 'skipped_capacity', entry_budget: null, exit_proceeds: null, issues: []}]};
  const result = {...output(packet), capital_backtest: {mode: 'fixed_sleeves', slots: 2, out_of_sample: book},
    out_of_sample: {trades: 2, portfolio_state: 'overlapping', total_return_pct: 999}};
  const p = page({canInvokeAction: () => true, invokeAction: async (_, input) => {submitted = input; return result;}});
  try {
    p.render({}, '1.4.0', result);
    assert.equal(p.field('model').value, 'fixed_sleeves');
    assert.equal(p.field('slots').value, '2');
    assert.equal(p.field('slots').disabled, false);
    assert.equal(p.field('capital-panel').hidden, false);
    assert.equal(p.text('validation-return'), '0.00%');
    assert.equal(p.text('validation-drawdown'), '--');
    assert.match(p.text('validation-status'), /完整回撤与风险比率不可确认/);
    assert.match(p.text('validation-capital-ledger'), /满仓跳过/);
    assert.match(p.text('validation-audit'), /每日开盘交易前后与收盘/);
    assert.doesNotMatch(p.text('validation-audit'), /仅按持有期末/);
    assert.equal(p.context().outOfSample.total_return_pct, null);
    assert.equal(p.context().capitalBacktest.outOfSample.total_return_pct, 0);
    assert.equal(p.context().capitalBacktest.outOfSample.curve, undefined);
    const series = p.charts.get('validation-capital-chart').series[0];
    assert.deepEqual(Array.from(series.data), [1, null, 1]);
    assert.equal(series.connectNulls, false);
    p.field('run').click(); await flush();
    assert.deepEqual(JSON.parse(JSON.stringify(submitted.capital_model)), packet.capital_model);
    changed(p, 'slots', '3');
    assert.equal(p.text('validation-return'), '--');
    assert.equal(p.field('capital-panel').hidden, true);
    assert.equal(p.context().capitalBacktest, undefined);
    assert.equal(p.charts.has('validation-capital-chart'), false);
    restore(p);
    assert.equal(p.field('model').value, 'diagnostic');
    assert.equal(p.field('slots').disabled, true);
    assert.equal(p.field('capital-panel').hidden, true);
  } finally {p.dom.window.close();}
});

test('execution evidence separates bar checks from fills and explains zero-volume legs', () => {
  const p = page();
  try {
    p.render({trades: 1, portfolio_state: 'incomplete'}, '1.5.0', {
      validation_audit: {calendar_policy: 'independent_exchange_calendar_exact_dates',
        execution_evidence: {policy: 'positive_daily_volume_required_for_open_price_diagnostic',
          planned_legs: 4, price_volume_verified_legs: 2, zero_volume_legs: 1, missing_evidence_legs: 0,
          pending_legs: 1, fill_guaranteed: false}},
      trades: [{decision_date: '2026-06-01', symbols: ['000001'], execution_state: 'unresolved',
        reason: 'unverified_asset_volume', execution_issues: [{symbol: '000001', date: '2026-06-02', side: 'buy', reason: 'zero_volume'}]}],
    });
    assert.match(p.text('validation-execution'), /2\/4项/);
    assert.match(p.text('validation-execution'), /不等于实际分仓成交数/);
    assert.match(p.text('validation-trades'), /000001 买入：全天成交量为零/);
    assert.equal(p.context().validationAudit.execution_evidence.fill_guaranteed, false);
    assert.equal(p.context().executionEvidenceState, 'legacy_limits_requires_rerun');
    changed(p, 'holding', '3');
    assert.equal(p.text('validation-execution'), '待核验计划买卖日的价格与成交量。');
    assert.equal(p.context().executionPolicy, undefined);
    restore(p);
    assert.match(p.text('validation-execution'), /旧结果未核验/);
    assert.equal(p.context().executionEvidenceState, 'legacy_execution_requires_rerun');
    p.render({}, '1.4.0', {...output(input()), verdict: 'diagnostic_ready',
      validation_audit: {calendar_policy: 'independent_exchange_calendar_exact_dates'},
      capital_backtest: {mode: 'fixed_sleeves', slots: 1, out_of_sample: {state: 'complete'}}});
    assert.equal(p.context().verdict, 'legacy_execution_requires_rerun');
    assert.match(p.text('validation-status'), /旧资金路径未核验成交量/);
  } finally {p.dom.window.close();}
});

test('raw limits, adverse direction, unavailable sources and legacy warnings agree with Agent', () => {
  const p = page();
  const limits = {dated_legs: 2, paired_legs: 2, adverse_legs: 1, unverified_legs: 0,
    feeds: [{symbol: '510300', feeds: {price: {source: 'fund_daily', status: 'ready', receivedAt: '2026-10-19'},
      limits: {source: 'etf_limit', status: 'ready', receivedAt: '2026-10-19'}}}]};
  const data = {verdict: 'diagnostic_ready', validation_audit: {calendar_policy: 'independent_exchange_calendar_exact_dates',
    execution_evidence: {policy: 'positive_daily_volume_required_for_open_price_diagnostic', price_limits: limits}},
    trades: [{decision_date: '2026-06-01', symbols: ['510300'], execution_state: 'unresolved', reason: 'adverse_price_limit',
      price_limit_checks: [{date: '2026-06-02', symbol: '510300', side: 'buy', state: 'adverse', reason: 'buy_at_upper_limit', rawOpen: 4.321, lowerLimit: 3.535, upperLimit: 4.321}]}]};
  try {
    p.render({trades: 0, portfolio_state: 'incomplete'}, '1.6.0', data);
    assert.match(p.text('validation-limits'), /2\/2项已配对/);
    assert.match(p.text('validation-limit-rows'), /4.321/);
    assert.match(p.text('validation-limit-rows'), /涨停买入/);
    assert.match(p.text('validation-limit-sources'), /fund_daily.*etf_limit/);
    assert.equal(p.context().verdict, 'adverse_limits_unresolved');
    assert.equal(p.context().priceLimitChecks[0].rawOpen, 4.321);
    limits.unverified_legs = 2; limits.paired_legs = 0; limits.adverse_legs = 0;
    limits.feeds[0].feeds.limits = {source: 'etf_limit', status: 'permission-denied', reason: '权限不足', usingSaved: true};
    data.trades = [];
    p.render({trades: 1, portfolio_state: 'complete', total_return_pct: 3}, '1.6.0', data);
    assert.equal(p.text('validation-return'), '3.00%');
    assert.match(p.text('validation-status'), /仅为理论测算/);
    assert.match(p.text('validation-limit-sources'), /权限不足.*旧缓存未用于核验/);
    assert.equal(p.context().verdict, 'limits_incomplete_theoretical');
    delete data.validation_audit.execution_evidence.price_limits;
    p.render({trades: 1, portfolio_state: 'complete'}, '1.5.0', data);
    assert.match(p.text('validation-status'), /旧结果未核验历史限价/);
    assert.equal(p.context().verdict, 'legacy_limits_requires_rerun');
    changed(p, 'holding', '3');
    assert.equal(p.text('validation-limit-rows'), '');
    assert.equal(p.text('validation-limit-sources'), '');
    assert.equal(p.context().priceLimitPolicy, undefined);
  } finally {p.dom.window.close();}
});

test('allocation selection during a running request discards its late result', async () => {
  let resolve;
  const p = page({canInvokeAction: () => true, invokeAction: () => new Promise(done => {resolve = done;})});
  try {
    restore(p); p.field('run').click(); await flush();
    changed(p, 'model', 'fixed_sleeves');
    resolve(output(input())); await flush();
    assert.equal(p.context().state, 'draft');
    assert.equal(p.text('validation-return'), '--');
    assert.equal(p.context().draft.capital_model.slots, 2);
  } finally {p.dom.window.close();}
});

test('history restores exact input and reruns original strategy with non-menu period and zero cost', async () => {
  let submitted;
  const p = page({canInvokeAction: () => true, invokeAction: async (_, packet) => {submitted = packet; return output(packet);}});
  try {
    restore(p);
    assert.equal(p.field('holding').value, '2');
    assert.equal(p.field('cost').value, '0');
    assert.equal(p.field('name').value, '历史样例');
    assert.equal(p.field('signal-list').children.length, 2);
    assert.equal(p.context().resultSource, 'history');
    p.field('run').click(); await flush();
    assert.deepEqual(JSON.parse(JSON.stringify(submitted)), input());
    assert.equal(p.context().resultSource, 'current');
    assert.equal(p.text('validation-return'), '3.00%');
  } finally {p.dom.window.close();}
});

test('every submitted field edit clears result, ledger and Agent evidence', () => {
  const p = page();
  try {
    for (const [name, value] of Object.entries({name: '新名称', source: 'czsc', benchmark: '510500', asof: '2026-07-01', holding: '5', cost: '25'})) {
      restore(p); changed(p, name, value);
      assert.equal(p.text('validation-return'), '--');
      assert.equal(p.text('validation-trades'), '');
      assert.equal(p.context().state, 'draft');
      assert.equal(p.context().outOfSample, undefined);
      assert.equal(p.context().snapshot, undefined);
    }
    restore(p); p.field('signal-list').querySelector('button').click();
    assert.equal(p.context().draftSignalCount, 1);
    assert.equal(p.text('validation-return'), '--');
  } finally {p.dom.window.close();}
});

test('late request success and failure cannot replace a changed draft or newer result', async () => {
  const requests = [];
  const p = page({canInvokeAction: () => true, invokeAction: (_, packet) => new Promise((resolve, reject) => requests.push({packet, resolve, reject}))});
  try {
    restore(p); p.field('run').click(); await flush();
    changed(p, 'cost', '50');
    assert.equal(requests[0].packet.cost_bps_per_side, 0);
    assert.equal(p.context().draft.cost_bps_per_side, 50);
    p.field('run').click(); await flush();
    requests[1].resolve(output(requests[1].packet)); await flush();
    requests[0].resolve(output(requests[0].packet)); await flush();
    assert.equal(p.context().input.cost_bps_per_side, 50);
    p.field('run').click(); await flush();
    changed(p, 'holding', '20');
    requests[2].reject(new Error('旧请求失败')); await flush();
    assert.equal(p.context().state, 'draft');
    assert.equal(p.field('alert').style.display, 'none');
    assert.equal(p.field('run').disabled, false);
  } finally {p.dom.window.close();}
});

test('history loading and workspace switching invalidate active work and clear private drafts', async () => {
  let resolve;
  const bridge = {config: {user: {id: 'u1'}, workspace: {id: 'w1'}}, canInvokeAction: () => true,
    invokeAction: (_, packet) => new Promise(done => {resolve = () => done(output(packet));})};
  const p = page(bridge);
  try {
    restore(p); p.field('run').click(); await flush();
    p.dom.window.document.dispatchEvent(new p.dom.window.CustomEvent('instock:history-loading'));
    resolve(); await flush();
    assert.equal(p.context().state, 'history-loading');
    assert.equal(p.text('validation-return'), '--');
    restore(p); p.field('run').click(); await flush();
    bridge.config.workspace.id = 'w2';
    p.dom.window.document.dispatchEvent(new p.dom.window.CustomEvent('vibedesk:init'));
    resolve(); await flush();
    assert.equal(p.context().draftSignalCount, 0);
    assert.equal(p.field('name').value, '页面策略验证');
    assert.equal(p.context().snapshot, undefined);
    assert.equal(p.text('validation-return'), '--');
  } finally {p.dom.window.close();}
});

test('legacy successful-only history does not reuse another draft for rerun; failed refresh clears result', async () => {
  const p = page({canInvokeAction: () => true, invokeAction: async () => {throw new Error('数据不可用');}});
  try {
    restore(p);
    p.render({trades: 2}, '1.0.1');
    assert.equal(p.field('signal-list').children.length, 0);
    assert.match(p.text('validation-input-state'), /缺少完整输入/);
    restore(p); p.field('run').click(); await flush();
    assert.equal(p.context().state, 'error');
    assert.equal(p.context().outOfSample, undefined);
    assert.equal(p.text('validation-return'), '--');
    assert.equal(p.text('validation-alert'), '数据不可用');
    assert.equal(p.field('run').disabled, false);
  } finally {p.dom.window.close();}
});

test('audited 1.2.0 history restores all planned signals including failed ones', () => {
  const p = page();
  try {
    const original = input();
    p.render({trades: 0}, '1.2.0', {strategy: original.strategy, as_of: original.as_of, benchmark: original.benchmark,
      rules: {holding_period_sessions: 2, cost_bps_per_side: 0},
      trades: original.signals.map(row => ({...row, execution_state: 'unresolved', reason: 'missing_asset_open'}))});
    assert.equal(p.field('signal-list').children.length, 2);
    assert.equal(p.field('cost').value, '0');
    assert.match(p.text('validation-input-state'), /完整参数和决策记录/);
    assert.match(p.text('validation-calendar'), /旧结果尚未核验独立交易日历/);
    assert.equal(p.context().verdict, 'legacy_calendar_requires_rerun');
  } finally {p.dom.window.close();}
});

test('independent calendar provenance reaches both page and Agent', () => {
  const p = page();
  try {
    p.render({trades: 1}, '1.3.0', {...output(input()), verdict: 'insufficient_evidence',
      validation_audit: {calendar_policy: 'independent_exchange_calendar_exact_dates', split_decision_date: '2026-06-03',
        calendar: {source: 'Tushare trade_cal / SSE', start: '2026-06-01', end: '2026-06-30', receivedAt: '2026-10-19'}}});
    assert.match(p.text('validation-calendar'), /独立日历：Tushare/);
    assert.equal(p.context().verdict, 'insufficient_evidence');
    assert.match(p.context().calendarPolicy, /不保证成交行情已到齐/);
  } finally {p.dom.window.close();}
});

test('real history drawer ignores reordered selections and responses arriving after edits', async () => {
  const pending = new Map();
  const records = ['first', 'second'].map(history_id => ({history_id, title: history_id, generated_at: '2026-06-30', parameters: {}}));
  const p = page({fetchAnalysis: url => url.includes('?') ? Promise.resolve({ok: true, json: async () => ({data: records})})
    : new Promise(resolve => pending.set(url.split('/').pop(), resolve))});
  try {
    const window = p.dom.window;
    window.document.body.insertAdjacentHTML('beforeend', '<button id="stock-suite-history-button">历史</button><section id="stock-suite-history"><div id="stock-suite-history-list"></div></section>');
    window.eval(readFileSync(new URL('../../bundled-runtimes/instock-analysis/instock/web/static/js/stock-suite-shell.js', import.meta.url), 'utf8'));
    await flush();
    const click = index => window.document.querySelectorAll('.stock-suite-history-item')[index].click();
    const respond = id => pending.get(id)({ok: true, json: async () => ({data: {history_id: id, payload: output({...input(), strategy: {...input().strategy, name: id}})}})});
    click(0); click(1);
    respond('second'); await flush();
    respond('first'); await flush();
    assert.equal(p.field('name').value, 'second');
    assert.equal(p.context().strategy.name, 'second');
    click(0); changed(p, 'name', '保留新草稿');
    respond('first'); await flush();
    assert.equal(p.field('name').value, '保留新草稿');
    assert.equal(p.context().state, 'draft');
    assert.equal(p.text('validation-return'), '--');
  } finally {p.dom.window.close();}
});
