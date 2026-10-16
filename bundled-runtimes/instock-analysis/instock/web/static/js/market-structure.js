(function () {
    'use strict';
    const escape = value => String(value == null ? '--' : value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    const number = (value, digits = 2) => value == null ? '--' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: digits});
    const pct = value => value == null ? '--' : `${value > 0 ? '+' : ''}${number(value)}%`;
    function unconfirm(value) {
        if (Array.isArray(value)) return value.map(unconfirm);
        if (!value || typeof value !== 'object') return value;
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, key === 'current' ? false : unconfirm(item)]));
    }
    window.InStockMarketStructure = function (root, publish) {
        let data = null, loading = false, error = '', days = '5', controller = null, historical = false;
        function context() {
            const result = loading || error || historical ? unconfirm(data) : data;
            if (result && (loading || error || historical)) result.relationship.text = '本次更新未确认，不输出指数与参与率关系';
            return {data: result, loading, error, days: Number(days), historical,
                note: '市场结构独立于下方榜单快照；只使用本区日期与样本，未确认数字仅供参考。'};
        }
        function render() {
            const evidence = context().data;
            if (!evidence) {
                root.innerHTML = `<h2>市场结构</h2><p role="status">${escape(historical ? '已选择历史复盘；该版本未保存市场结构，请刷新读取当前结构。' : error || '正在读取同日市场结构…')}</p><button type="button" class="desk-button" data-structure-refresh ${loading ? 'disabled' : ''}>刷新结构</button>`;
                return;
            }
            const breadth = evidence.breadth, turnover = evidence.turnover, summary = turnover.summary || {};
            const max = Math.max(1, ...(breadth.buckets || []).map(row => row.count));
            const title = loading ? '正在更新，旧数据暂不确认' : error ? '更新失败，保留数据仅供参考' : evidence.current ? '所列窗口已核对' : '部分证据待核验';
            const metric = (name, value, note) => `<div><span>${name}</span><strong>${value}</strong><small>${escape(note)}</small></div>`;
            root.innerHTML = `<header class="market-structure-head"><h2>市场结构</h2><span role="status">${escape(evidence.asOf)} · ${title}</span><button type="button" class="desk-button" data-structure-refresh ${loading ? 'disabled' : ''}>刷新结构</button></header>
                ${error ? `<p class="structure-warning">${escape(error)}</p>` : ''}
                <div class="market-structure-metrics">
                  ${metric('样本上涨比例', `${number(breadth.upRatioPct)}%`, `${breadth.validCount || 0} 只有效涨跌幅 · ${breadth.current ? '已核对' : '待核验'}`)}
                  ${metric('涨 / 跌 / 平', `${number(breadth.up, 0)} / ${number(breadth.down, 0)} / ${number(breadth.flat, 0)}`, `无有效成交／价格 ${breadth.inactiveCount || 0} · 缺涨跌幅 ${breadth.missingPctCount || 0}`)}
                  ${metric('样本涨跌中位数', pct(breadth.medianPct), '非持仓收益、非等权指数收益')}
                  ${metric('Top20成交占比', `${number(summary.top20SharePct)}%`, `样本成交 ${number(summary.sampleTurnoverYi)} 亿元 · ${turnover.current ? '已核对' : '待核验'}`)}
                </div>
                <p class="market-structure-conclusion">${escape(loading || error ? '本次更新未确认，不输出指数与参与率关系' : evidence.relationship.text)}</p>
                <div class="market-structure-grid">
                  <section aria-label="样本涨跌分布"><h3>当日参与分布</h3><div class="structure-distribution">${(breadth.buckets || []).map((row, index) => `<div><span>${escape(row.label)}</span><i style="--bar-width:${row.count / max * 100}%;--bar-color:var(${index < 3 ? '--instock-negative' : index > 3 ? '--instock-positive' : '--instock-text-muted'})"></i><b>${number(row.count, 0)}</b></div>`).join('')}</div><p>${escape(breadth.note)}</p></section>
                  <section aria-label="指数与风格对照"><div class="market-structure-head"><h3>指数与风格</h3><div class="structure-windows" aria-label="指数比较窗口">${[1, 5, 20].map(day => `<button type="button" data-structure-days="${day}" aria-pressed="${String(day) === days}">${day}日</button>`).join('')}</div></div>
                    <div class="structure-table-scroll"><table><thead><tr><th>价格指数</th><th>${days}日涨跌</th><th>期初 → 期末</th></tr></thead><tbody>${evidence.indices.map(row => { const window = row.windows[days]; return `<tr><td>${escape(row.name)}<small>${escape(row.code)}</small></td><td>${pct(window.returnPct)}${window.current ? '' : '<small>未确认</small>'}</td><td>${escape(window.baseDate)} → ${escape(window.end)}${window.reason ? `<small>${escape(window.reason)}</small>` : ''}</td></tr>`; }).join('')}</tbody></table></div>
                    <div class="structure-spreads">${evidence.styles.map(row => `<div><span>${escape(row.label)}</span><strong>${number(row.windows[days].spreadPp)} 个百分点${row.windows[days].current ? '' : ' · 未确认'}</strong></div>`).join('')}</div>
                  </section>
                </div><details class="structure-method"><summary>数据口径与边界</summary>${evidence.notes.map(note => `<p>${escape(note)}</p>`).join('')}<p>Tushare daily / index_daily；日线成交额由千元换算人民币亿元。沪深300、500、1000存在不同成分与行业权重，风格差不是纯因子归因。</p></details>`;
        }
        root.addEventListener('click', event => {
            if (event.target.closest('[data-structure-refresh]')) { api.refresh(true); return; }
            const button = event.target.closest('[data-structure-days]');
            if (!button) return;
            days = button.dataset.structureDays; render(); publish();
        });
        const api = {context, historical() { controller?.abort(); data = null; loading = false; historical = true; render(); publish(); },
            async refresh(force) {
                controller?.abort(); const request = new AbortController(); controller = request;
                historical = false; loading = true; error = ''; render(); publish();
                try {
                    const response = await fetch('/api/v1/market-workbench/structure?refresh=' + (force ? '1' : '0'), {signal: request.signal});
                    if (!response.ok) throw new Error(`市场结构读取失败（${response.status}）`);
                    const payload = await response.json();
                    const next = payload.ok === true ? payload.data : payload;
                    if (next.schemaVersion !== 'newma-desk.market-structure.v1') throw new Error('市场结构数据格式不匹配');
                    if (!request.signal.aborted) data = next;
                } catch (reason) { if (!request.signal.aborted) error = reason.message || '市场结构读取失败'; }
                finally { if (!request.signal.aborted) { loading = false; render(); publish(); } }
            }};
        return api;
    };
})();
