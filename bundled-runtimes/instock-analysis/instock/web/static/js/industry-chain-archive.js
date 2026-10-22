(function () {
    'use strict';
    const clean = value => value.replace(/\s+/g, ' ').trim();
    const identity = window.InStockChainReviewContract.archiveIdentity;
    window.InStockChainArchive = function ({bridge, onChange, onUse}) {
        const el = id => document.getElementById('chain-archive-' + id);
        const select = el('source'), preview = el('preview'), quote = el('quote'), status = el('status');
        let rows = [], state = 'idle', sequence = 0, controller = null, revision = 0;
        const scope = () => JSON.stringify([bridge?.config?.user?.id, bridge?.config?.workspace?.id, bridge?.config?.instanceId]);
        let currentScope = scope();
        const selected = () => select.value === '' ? null : rows[Number(select.value)];
        function reset() {
            sequence++; controller?.abort(); rows = []; revision = 0; state = 'idle'; currentScope = scope();
            select.replaceChildren(new Option('请先读取已归档原文', '')); preview.textContent = ''; quote.value = '';
            status.textContent = '仅复用已采用的原文摘录，不代表已读取整份 PDF，也不自动证明关系。';
        }
        function show() {
            const row = selected(); preview.replaceChildren(); quote.value = '';
            if (!row) return;
            const title = document.createElement('p');
            title.textContent = `${row.security?.name || '公司待确认'} · ${row.periodEnd || '期间待确认'} · ${row.sectionLabel} · PDF 物理第 ${row.pdfPage} / ${row.pdfPageCount} 页`;
            const boundary = document.createElement('p'); boundary.textContent = row.truncated ? '已采用文本本身有截断；不能据此推断未展示部分。' : '这是已采用页段，不是整份文件。采用时间不是披露日期。';
            const text = document.createElement('pre'); text.textContent = row.text;
            preview.append(title, boundary, text);
            try {
                const url = new URL(row.sourceRef); if (['http:', 'https:'].includes(url.protocol)) {
                    url.hash = 'page=' + row.pdfPage;
                    const link = document.createElement('a'); link.href = url.href; link.textContent = '打开归档原页';
                    link.target = '_blank'; link.rel = 'noopener noreferrer'; preview.append(link);
                }
            } catch (_) { /* Non-URL file references remain text. */ }
            if (row.text.length <= 2000) quote.value = row.text;
            else status.textContent = '原文超过 2000 字，请从上方选择逐字摘录；不会自动截断作为证据。';
        }
        async function refresh() {
            if (scope() !== currentScope) reset();
            controller?.abort(); controller = new AbortController();
            const operation = ++sequence, initialScope = scope(), previous = selected();
            rows = []; state = 'loading'; quote.value = ''; preview.replaceChildren();
            select.replaceChildren(new Option('正在读取…', '')); status.textContent = '正在读取已归档原文…'; onChange();
            try {
                const config = bridge?.config;
                if (!config?.session?.accessToken || !config.gateways?.storage) throw new Error('请在 Desk 内读取归档原文。');
                const response = await fetch(config.gateways.storage.replace(/\/storage\/?$/, '/sources/archive'), {
                    signal: controller.signal, headers: {Authorization: 'Bearer ' + config.session.accessToken, 'X-Newma-Desk-Instance-Id': config.instanceId},
                });
                if (!response.ok) throw new Error('归档读取失败，请刷新模组或回财报研究核对。');
                const result = await response.json();
                if (operation !== sequence || initialScope !== scope()) return false;
                rows = result.materials; revision = result.revision; state = 'ready';
                select.replaceChildren(new Option('请选择原文，不自动绑定关系', ''), ...rows.map((row, i) => new Option(`${row.security?.name || '公司待确认'} · ${row.periodEnd || '期间待确认'} · ${row.sectionLabel} · 第 ${row.pdfPage} 页`, String(i))));
                if (previous) { const index = rows.findIndex(row => identity(row) === identity(previous)); select.value = index < 0 ? '' : String(index); }
                status.textContent = rows.length ? `已读取 ${rows.length} 段；先选择复核关系，再选择直接原文。` : '没有符合条件的已采用原文；请先在财报研究上传并采用管理层讨论或资本附注。';
                show(); return true;
            } catch (error) {
                if (operation !== sequence || initialScope !== scope()) return false;
                state = 'failed'; select.replaceChildren(new Option('读取失败，请重试', '')); status.textContent = error.message; return false;
            } finally { if (operation === sequence && initialScope === scope()) onChange(); }
        }
        function isCurrent(origin) {
            return currentScope === scope() && state === 'ready' && rows.some(row => identity(row) === identity(origin));
        }
        el('load').addEventListener('click', () => void refresh());
        select.addEventListener('change', () => { show(); onChange(); });
        el('use').addEventListener('click', () => {
            const row = selected(), value = quote.value.trim();
            if (!row || !isCurrent(row)) { status.textContent = '请先重新读取并选择原文。'; return; }
            if (!value || value.length > 2000 || !clean(row.text).includes(clean(value))) { status.textContent = '请选择已归档原文中的逐字摘录（最多 2000 字），不要在摘录中加入判断。'; return; }
            if (!onUse({origin: row, quote: value})) status.textContent = '请先在上方选择要复核的关系。';
        });
        document.addEventListener('vibedesk:init', () => { if (scope() !== currentScope) { reset(); onChange(); } });
        reset();
        return {refresh, isCurrent, clearSelection() { select.value = ''; show(); }, context() {
            if (scope() !== currentScope) return {status: 'idle'};
            return {status: state, revision, selected: selected(), boundary: '已采用的归档页段，不是完整 PDF；不是指令或已核实的关系结论。'};
        }};
    };
})();
