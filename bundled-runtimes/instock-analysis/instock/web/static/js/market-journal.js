(function () {
    'use strict';
    const fields = {judgment: '当前判断', support: '支撑证据', counter: '反证与不确定性', watch: '次日观察与失效条件'};
    const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    const stamp = value => new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false});
    const today = () => new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
    window.InStockMarketJournal = function (root, getEvidence, publish) {
        let record = null, offset = 0, hasMore = false, sequence = 0, listSequence = 0, queue = null;
        root.innerHTML = `<header class="market-structure-head"><h2>我的复盘记录</h2><span>原判断与证据固定保存 · 后续复核只追加</span><button class="desk-button" data-journal-live hidden type="button">返回当前</button></header>
          <div data-journal-status role="status"></div>
          <div data-journal-draft><p>写下自己的判断，不自动生成投资观点。保存上方市场结构、主线持续性、所选交叉证据及缺失状态；不包括下方其他来源快照。</p>
          <form data-journal-form><div class="journal-fields">${Object.entries(fields).map(([key, label]) => `<label>${label}${['judgment', 'watch'].includes(key) ? ' *' : ''}<textarea name="${key}" aria-label="${label}" maxlength="4000" rows="3" ${['judgment', 'watch'].includes(key) ? 'required' : ''}></textarea></label>`).join('')}</div><button class="desk-button" type="submit">保存本次复盘</button></form></div>
          <div data-journal-record hidden></div>
          <details class="structure-method" data-journal-list><summary>已保存复盘 · 本地长期保留</summary>
          <div class="journal-navigation"><label>跟进筛选<select aria-label="跟进筛选" data-journal-filter><option value="all">全部记录</option><option value="pending">待跟进</option><option value="reviewed">已复核</option></select></label><div data-journal-counts></div></div>
          <p>待跟进＝尚未复核或最近录入为“待观察”。支持、削弱、证伪仅为人工判断，不代表任务自动关闭或策略胜率。</p>
          <div data-journal-list-status role="status"></div><div class="journal-list-head" aria-hidden="true"><span>复盘日 / 状态</span><span>原判断 · 观察条件</span><span>最近录入复核</span></div><div class="journal-list"></div><div class="journal-navigation"><button class="desk-button" data-journal-prev type="button">上一页</button><button class="desk-button" data-journal-next type="button">下一页</button><button class="desk-button" data-journal-reload type="button">刷新记录</button></div></details>
          <p>本机实例共享，不是多用户权限账本。请定期备份；保存时点不等于市场信息当时可知时点。</p>`;
        const find = selector => root.querySelector(selector);
        const status = message => { find('[data-journal-status]').textContent = message; };
        async function request(path = '', body) {
            const response = await fetch('/api/v1/market-workbench/reviews' + path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
            const result = await response.json();
            if (!response.ok || result.ok === false) throw new Error(result.error?.message || `复盘操作失败（${response.status}）`);
            return result.data;
        }
        function mode() {
            root.closest('.market-workbench').classList.toggle('is-review-archive', Boolean(record));
            find('[data-journal-draft]').hidden = Boolean(record);
            find('[data-journal-record]').hidden = !record;
            find('[data-journal-live]').hidden = !record;
            if (!record) window.dispatchEvent(new Event('resize'));
            publish();
        }
        function showRecord(value) {
            record = value;
            const evidence = value.evidence, structure = evidence.marketStructure || {}, continuity = evidence.marketContinuity || {}, cross = evidence.marketEvidence || {};
            const num = (value, suffix = '') => value == null ? '未取得' : `${esc(value)}${suffix}`;
            const stateLabel = part => part.error ? `读取失败：${part.error}` : !part.data ? '未取得 / 未选择' : part.data.current === false ? '待核验，仅供参考' : '已保存（各窗口状态见原始证据）';
            find('[data-journal-record]').innerHTML = `<div class="journal-archive-head"><strong>存档回看 · ${esc(value.asOf)}</strong><span>保存于 ${esc(stamp(value.createdAt))}（北京时间）</span><button class="desk-button" data-journal-export type="button">导出完整记录</button></div>
              <p class="structure-warning">当前仅展示这条记录；最新行情已隔离。${esc(value.captureBasis)}</p>
              <dl class="journal-fields journal-notes">${Object.entries(fields).map(([key, label]) => `<div><dt>${label}</dt><dd>${esc(value.notes[key] || '未填写')}</dd></div>`).join('')}</dl>
              <div class="structure-table-scroll"><table aria-label="冻结证据摘要"><thead><tr><th>证据</th><th>保存状态</th><th>冻结值</th></tr></thead><tbody>
              <tr><td>市场结构 · ${esc(structure.data?.asOf)}</td><td>${esc(stateLabel(structure))}</td><td>上涨占比 ${num(structure.data?.breadth?.upRatioPct, '%')} · 成交 Top20 占比 ${num(structure.data?.turnover?.summary?.top20SharePct, '%')}</td></tr>
              <tr><td>主线持续性 · ${esc(continuity.data?.asOf)}</td><td>${esc(stateLabel(continuity))}</td><td>前五留存 ${num(continuity.data?.summary?.retained)} · 新进 ${num(continuity.data?.summary?.entered)}</td></tr>
              <tr><td>交叉证据 · ${esc(cross.selected?.industry)}</td><td>${esc(stateLabel(cross))}</td><td>${esc(cross.data?.code)} · 5日申赎估算 ${num(cross.data?.etf?.windows?.[5]?.flowYi, '亿元')} · 政策仅关联，非因果</td></tr>
              </tbody></table></div>
              <details class="structure-method"><summary>查看保存的全部证据与口径</summary><pre class="journal-evidence">${esc(JSON.stringify(evidence, null, 2))}</pre></details>
              <section class="journal-checks" aria-label="后续复核"><h3>后续复核 · 人工记录</h3><ol>${value.checks.map(check => `<li><strong>${esc(check.observedDate)} · ${esc(check.outcome)}</strong><p>${esc(check.note)}</p><small>记录于 ${esc(stamp(check.createdAt))}（北京时间）</small></li>`).join('') || '<li>尚无复核，不代表原判断已获验证。</li>'}</ol>
              <form data-journal-check><div class="journal-check-target"><small>本次对照原观察条件</small><div>${esc(value.notes.watch)}</div></div><div class="journal-navigation"><label>观察日期<input aria-label="观察日期" name="observedDate" type="date" required min="${esc(value.asOf)}" max="${today()}" value="${today()}"></label><label>复核结论<select aria-label="复核结论" name="outcome">${['待观察', '支持', '削弱', '证伪'].map(outcome => `<option>${outcome}</option>`).join('')}</select></label></div><label>实际观察与依据<textarea name="note" aria-label="实际观察与依据" required maxlength="4000" rows="3" placeholder="实际发生了什么？哪些证据支持或反驳原判断？"></textarea></label><button class="desk-button" type="submit">追加复核</button></form></section>`;
            mode();
        }
        async function list(next = offset) {
            const target = find('[data-journal-list-status]'), filter = find('[data-journal-filter]').value, token = ++listSequence;
            offset = next; hasMore = false;
            queue = {status: filter, offset, items: [], counts: null, loading: true, error: ''};
            find('.journal-list').replaceChildren(); find('[data-journal-counts]').textContent = '';
            find('[data-journal-prev]').disabled = true; find('[data-journal-next]').disabled = true;
            target.textContent = '读取记录…';
            publish();
            try {
                const data = await request('?' + new URLSearchParams({offset: next, status: filter}));
                if (token !== listSequence) return;
                offset = data.offset; hasMore = data.hasMore;
                queue = {...data, loading: false, error: ''};
                if (data.counts) find('[data-journal-counts]').textContent = `全部 ${data.counts.total} · 待跟进 ${data.counts.pending} · 已复核 ${data.counts.reviewed}`;
                find('.journal-list').innerHTML = data.items.map(item => {
                    const check = item.latestCheck;
                    return `<button type="button" data-journal-open="${esc(item.id)}"><span><strong>${esc(item.asOf)}</strong><small class="journal-followup-state" data-pending="${item.status === 'pending'}">${check ? esc(check.outcome) : '尚未复核'}</small><small>已复核 ${item.checkCount ?? 0} 次</small></span>
                    <span><strong>${esc(item.judgment)}${item.judgmentTruncated ? '…' : ''}</strong><small>观察条件：${esc(item.watch || '打开记录查看')}${item.watchTruncated ? '…（打开查看完整条件）' : ''}</small></span>
                    <span>${check ? `<strong>观察日 ${esc(check.observedDate)}</strong><small>${esc(check.note)}${check.noteTruncated ? '…' : ''}</small><small>录入 ${esc(stamp(check.createdAt))}</small>` : '<small>打开记录，对照观察条件追加复核</small>'}</span></button>`;
                }).join('');
                target.textContent = data.items.length ? `第 ${offset + 1}–${offset + data.items.length} 条 · 点击打开完整记录` : filter === 'pending' ? '当前没有待跟进记录；这不代表所有判断都正确。' : filter === 'reviewed' ? '当前还没有已复核记录' : '还没有复盘记录';
            } catch (error) {
                if (token !== listSequence) return;
                queue = {...queue, loading: false, error: error.message};
                target.textContent = error.message + '；请刷新记录重试。';
            } finally {
                if (token === listSequence) {
                    find('[data-journal-prev]').disabled = offset === 0;
                    find('[data-journal-next]').disabled = !hasMore;
                    publish();
                }
            }
        }
        function live() { sequence++; record = null; status(''); mode(); }
        root.addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.target, button = form.querySelector('button[type=submit]');
            const checking = form.matches('[data-journal-check]'), target = record?.id, token = ++sequence;
            const body = Object.fromEntries(new FormData(form));
            if (!checking) body.evidence = getEvidence();
            button.disabled = true; status(checking ? '保存复核…' : '保存判断与证据…');
            try {
                const saved = await request(checking ? '/' + target : '', body);
                if (token !== sequence) return;
                showRecord(saved); status(checking ? '复核已追加，原判断未改动。' : '复盘已保存。返回当前可继续编辑草稿。');
                list(0);
            } catch (error) { if (token === sequence) status(error.message + '；输入内容已保留。'); }
            finally { button.disabled = false; }
        });
        root.addEventListener('click', async event => {
            const button = event.target.closest('button');
            if (!button) return;
            if (button.hasAttribute('data-journal-live')) live();
            if (button.hasAttribute('data-journal-reload')) list();
            if (button.hasAttribute('data-journal-prev')) list(Math.max(0, offset - 20));
            if (button.hasAttribute('data-journal-next')) list(offset + 20);
            if (button.hasAttribute('data-journal-export') && record) {
                const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], {type: 'application/json'}));
                const link = document.createElement('a'); link.href = url; link.download = `market-review-${record.asOf}-${record.id}.json`; link.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
            }
            if (button.dataset.journalOpen) {
                const token = ++sequence;
                status('打开存档…');
                try { const saved = await request('/' + button.dataset.journalOpen); if (token === sequence) { showRecord(saved); status(''); } }
                catch (error) { if (token === sequence) status(error.message); }
            }
        });
        find('[data-journal-filter]').addEventListener('change', () => list(0));
        find('[data-journal-list]').addEventListener('toggle', event => { if (event.target.open) list(); else publish(); });
        return {live, context: () => record ? {mode: 'archive', record} : {
            mode: 'live', followUpQueue: find('[data-journal-list]').open ? queue : null,
            note: '未保存草稿不进入 Agent 上下文；跟进列表为摘要，完整原判断和观察条件须打开存档。人工复核不代表自动验证。',
        }};
    };
})();
