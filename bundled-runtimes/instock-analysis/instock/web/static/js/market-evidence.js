(function () {
    'use strict';
    const esc = value => String(value == null ? '—' : value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
    const num = (value, unit = '') => value == null ? '—' : `${Number(value).toLocaleString('zh-CN', {maximumFractionDigits: 4})}${unit}`;
    const stamp = value => {
        if (!value) return '—';
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false});
    };
    const sourceLink = (url, label) => /^https?:\/\//i.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label);
    window.InStockMarketEvidence = function (root, publish) {
        let selected = null, data = null, loading = false, error = '', controller;
        const context = () => ({selected, data, loading, error, note: '按需核对所选ETF和政策关联候选；不产生行业资金合计或因果结论。'});
        function render() {
            if (!selected) {
                root.innerHTML = '<p>点击上方行业名称，核对对应 ETF 的申赎、跟踪指数与政策线索。</p>';
                return;
            }
            const header = `<header class="market-structure-head"><h2>${esc(selected.industry)} · 交叉证据</h2><span>${esc(selected.asOf)} · ${esc(selected.code)}</span><button class="desk-button" data-evidence-refresh type="button" ${loading ? 'disabled' : ''}>重查证据</button></header>`;
            if (!data) { root.innerHTML = `${header}<p role="status">${esc(loading ? '正在核对目录、份额净值及已有政策记录…' : error || '证据未取得')}</p>`; return; }
            const {catalog, mapping, etf, policies} = data;
            const item = catalog.item;
            root.innerHTML = `${header}<p class="market-structure-conclusion">${esc(item?.name || mapping.configuredName)} ${esc(data.code)} → ${esc(item?.indexName || '跟踪指数待核验')} ${esc(item?.indexCode || '')}<br>
                <small>${mapping.proxyType === 'direct' ? '配置行业代理；不等于整个行业' : '非直接行业代理'} · ${esc(mapping.proxyNote || mapping.basis)} · 目录${catalog.status === 'ready' && !catalog.usingSaved ? '已读取' : '未确认'}（${esc(stamp(catalog.receivedAt))} 北京时间）</small></p>
                <div class="market-evidence-grid">
                  <section aria-label="所选ETF申赎"><h3>ETF 申赎估算</h3>${etf ? `<div class="structure-table-scroll"><table><thead><tr><th>窗口</th><th>估算净额（亿元）</th><th>占期初规模</th><th>状态</th></tr></thead><tbody>${[1, 5, 20].map(day => { const w = etf.windows[day]; return `<tr><td>${day}日<small>${esc(w.baseDate)} → ${esc(w.end)}</small></td><td>${num(w.flowYi)}</td><td>${num(w.strengthPct, '%')}</td><td>${w.current ? '窗口已核对' : '待核验'}<small>${esc(w.reason || '')}</small></td></tr>`; }).join('')}</tbody></table></div><p>${esc(etf.source)} · 数据截至 ${esc(etf.asOf)}<br>${esc(etf.note)} ${esc(etf.sourceNote)}</p>` : `<p role="status">${esc(catalog.reason || '当前目录没有匹配ETF，未把缺失申赎填成零。')}</p>`}
                  <p>份额变化 × 当日净值；不是成交额，也不是整个行业净流入。按截止日重算，历史可知时点未验证。</p></section>
                  <section aria-label="关联政策候选"><h3>政策线索 · 事后核对</h3><p>${esc(policies.start)} → ${esc(policies.end)} · 匹配 ${policies.matchedCount} 条${policies.matchedCount > policies.items.length ? `，展示最近${policies.items.length}条` : ''}</p>
                    ${policies.items.length ? `<ol class="market-policy-list">${policies.items.map(policy => `<li><strong>${sourceLink(policy.sourceUrl, policy.title)}</strong><p>${esc(policy.institution)} · ${esc(policy.publishedDate)}<br>${esc(policy.dateBasis)}</p>
                        <p>对应依据：${policy.matchedEntities.map(entity => `${esc(entity.displayName)}「${esc(entity.evidence || '实体记录')}」`).join('；')}（实体关联，不是受益结论）</p>
                        <small>${esc(policy.timingLabel)} · 首次入库 ${esc(stamp(policy.firstSeenAt))}（北京时间）<br>${policy.documentStatus === 'missing' ? '尚未保存正文，点击标题核验原文' : `已有正文记录 · 获取 ${esc(stamp(policy.documentFetchedAt))}（北京时间）`}</small></li>`).join('')}</ol>` : '<p role="status">当前缓存没有符合日期与实体条件的已发布政策。不是“没有政策影响”。</p>'}
                    <p>${esc(policies.note)}</p></section>
                </div><details class="structure-method"><summary>对应关系与时间口径</summary>${data.notes.map(note => `<p>${esc(note)}</p>`).join('')}</details>`;
        }
        async function load(force) {
            controller?.abort(); const request = new AbortController(); controller = request;
            const target = selected;
            data = null; loading = true; error = ''; render(); publish();
            try {
                const query = new URLSearchParams({code: target.code, asOf: target.asOf, refresh: force ? '1' : '0'});
                const response = await window.InStockNewmaDesk.fetchAnalysis('/api/v1/market-workbench/evidence?' + query, {signal: request.signal});
                if (!response.ok) throw new Error(response.status === 403 ? '交叉证据尚未获得当前工作区授权' : `交叉证据读取失败（${response.status}）`);
                const payload = await response.json(), value = payload.ok ? payload.data : payload;
                if (value.schemaVersion !== 'newma-desk.market-evidence.v1' || value.code.split('.')[0] !== target.code || value.requestedDate !== target.asOf) throw new Error('证据对象或日期不匹配');
                if (!request.signal.aborted) data = value;
            } catch (reason) { if (!request.signal.aborted) error = reason.message || '交叉证据读取失败'; }
            finally { if (!request.signal.aborted) { loading = false; render(); publish(); } }
        }
        root.addEventListener('click', event => { if (event.target.closest('[data-evidence-refresh]') && selected) load(true); });
        const api = {context, select(row, asOf) {
            controller?.abort(); selected = row ? {code: row.code, industry: row.industry, asOf} : null;
            data = null; error = ''; loading = false;
            if (selected) return load(false);
            render(); publish();
        }};
        document.addEventListener('instock:session-changed', () => api.select(null));
        render();
        return api;
    };
})();
