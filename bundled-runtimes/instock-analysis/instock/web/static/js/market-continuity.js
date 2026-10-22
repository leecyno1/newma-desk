(function () {
    'use strict';
    const esc = value => String(value == null ? '—' : value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    const signed = value => value == null ? '—' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`;
    window.InStockMarketContinuity = function (root, publish, reviewDate, selectEvidence) {
        let data = null, loading = false, error = '', historical = false, all = false, controller;
        function context() {
            const unavailable = loading || error || historical;
            const evidence = !data ? null : unavailable ? {...data, current: false,
                rows: data.rows.map(row => ({...row, current: false, phase: '待核验', rankChange: null, top5Periods: null})),
                summary: {retained: null, entered: null, leaderPeriods: null, leaderChanges: null}} : data;
            return {data: evidence, loading, error, historical, showAll: all,
                note: '只比较本区日期的价格成交回放排名；与市场结构、政策、资金不合成结论。'};
        }
        function render() {
            const value = context().data;
            const status = historical ? '历史记录未保存持续性证据，请刷新读取当前复盘。' : loading ? '正在读取轮动回放，旧结果暂不确认…' : error || (value?.current ? '同池、同口径排名已核对' : '证据不足，暂不确认持续性');
            const header = `<header class="market-structure-head"><h2>主线与持续性</h2><span role="status">${esc(value?.asOf || '')} · ${esc(status)}</span><button class="desk-button" type="button" data-continuity-refresh ${loading ? 'disabled' : ''}>刷新主线</button></header>`;
            if (!value) { root.innerHTML = header; return; }
            const summary = value.summary;
            const visible = all ? value.rows : value.rows.filter(row => row.rank <= 5 || row.phase === '退出前五');
            const metric = (label, number, note) => `<div><span>${label}</span><strong>${esc(number)}</strong><small>${esc(note)}</small></div>`;
            root.innerHTML = `${header}
                <div class="market-structure-metrics">
                  ${metric('前五保留', summary.retained == null ? null : `${summary.retained} / 5`, `${value.comparisonDate || '—'} → ${value.asOf || '—'}`)}
                  ${metric('新进前五', summary.entered, '成员更替，不等于资金扩散')}
                  ${metric('榜首连续观测', summary.leaderPeriods, `近 ${value.dates.length} 期 · 不是胜率`)}
                  ${metric('榜首切换', summary.leaderChanges, `${value.rows.length} / ${value.universeSize} 个配置代理`)}
                </div>
                <p class="market-structure-conclusion">${value.current ? '先看领先是否留存，再看绝对涨幅；弱市中的相对领先也可能仍在下跌。' : '本次持续性未确认；轨迹与涨幅只保留为参考。'} ${esc(value.reasons.join('；'))}</p>
                <div class="market-structure-head"><span>价格成交回放 · ${esc(value.dates[0])} → ${esc(value.dates.at(-1))}</span><button type="button" class="desk-button" data-continuity-all aria-pressed="${all}">${all ? '仅看前五及退出' : '查看全部候选'}</button></div>
                <div class="structure-table-scroll continuity-scroll"><table><thead><tr><th>行业 / 信号代理</th><th>回放排名</th><th>5期变化</th><th>前五次数</th><th>20日涨幅 / 超额</th><th>近${value.dates.length}期排名 · 左旧右新</th><th>成员变化</th></tr></thead><tbody>${visible.map(row => `<tr>
                  <td><button type="button" class="continuity-select" data-market-evidence="${esc(row.code)}" aria-label="核对${esc(row.industry)}证据" ${loading || error || historical ? 'disabled' : ''}>${esc(row.industry)} ↗</button><small>${esc(row.name)} ${esc(row.code)}</small><small>${esc(row.signalMode === 'industry_index' ? '行业指数信号' : 'ETF代理信号')}${row.proxyType !== 'direct' ? ' · 非直接代理' : ''}</small></td>
                  <td>${esc(row.rank)}${row.current ? '' : '<small>未确认</small>'}</td><td>${row.rankChange == null ? '—' : `${row.rankChange > 0 ? '+' : ''}${row.rankChange}`}<small>正数为名次上升</small></td>
                  <td>${esc(row.top5Periods)} / ${row.observedPeriods}</td><td>${signed(row.price20dPct)}%<small>${signed(row.relative20dPp)} 个百分点</small></td>
                  <td><div class="continuity-ranks" aria-label="${esc(row.industry)}排名轨迹">${row.ranks.map((rank, index) => `<span class="${rank != null && rank <= 5 ? 'is-leading' : ''}" title="${esc(value.dates[index])} · ${rank == null ? '缺失' : '第' + rank + '名'}">${esc(rank)}</span>`).join('')}</div></td><td>${esc(row.phase)}</td></tr>`).join('')}</tbody></table></div>
                <details class="structure-method"><summary>代理关系、来源与结论边界</summary><p>${esc(value.source)}</p>${value.notes.map(note => `<p>${esc(note)}</p>`).join('')}<p>前五之外不等于退潮；成员换手不等于上涨行业扩散。点击行业按准确ETF代码和政策实体核对证据，交叉证据不回填排名。</p>${visible.filter(row => row.proxyNote).map(row => `<p>${esc(row.industry)}：${esc(row.proxyNote)}</p>`).join('')}</details>`;
        }
        root.addEventListener('click', event => {
            if (event.target.closest('[data-continuity-refresh]')) api.refresh(true);
            if (event.target.closest('[data-continuity-all]')) { all = !all; render(); publish(); }
            const button = event.target.closest('[data-market-evidence]');
            if (button && !button.disabled) selectEvidence(data.rows.find(row => row.code === button.dataset.marketEvidence), data.requestedDate);
        });
        const api = {context,
            pending() { controller?.abort(); loading = true; error = ''; historical = false; selectEvidence(null); render(); publish(); },
            historical() { controller?.abort(); data = null; error = ''; loading = false; historical = true; selectEvidence(null); render(); publish(); },
            async refresh(force) {
                controller?.abort(); const request = new AbortController(); controller = request;
                selectEvidence(null);
                historical = false; loading = true; error = ''; render(); publish();
                try {
                    const day = reviewDate();
                    if (!day) throw new Error('请先成功刷新市场结构，确认复盘截止日');
                    const query = new URLSearchParams({window: '60', benchmark: '510300', asOf: day, view: 'continuity', refresh: force ? '1' : '0'});
                    const response = await window.InStockNewmaDesk.fetchAnalysis('/api/v1/rotations/snapshots?' + query, {signal: request.signal});
                    if (!response.ok) throw new Error(response.status === 403 ? '主线证据尚未获得当前工作区授权' : `主线证据读取失败（${response.status}）`);
                    const payload = await response.json(), next = payload.ok ? payload.data : payload;
                    if (next.schemaVersion !== 'newma-desk.market-continuity.v1') throw new Error('主线证据格式不匹配');
                    if (!request.signal.aborted) data = next;
                } catch (reason) { if (!request.signal.aborted) error = reason.message || '主线证据读取失败'; }
                finally { if (!request.signal.aborted) { loading = false; render(); publish(); } }
            }};
        document.addEventListener('instock:session-changed', () => {
            controller?.abort(); data = null; loading = false; historical = false; all = false;
            error = '会话授权已变化，请重新读取当前工作区数据'; selectEvidence(null); render(); publish();
        });
        render();
        return api;
    };
})();
