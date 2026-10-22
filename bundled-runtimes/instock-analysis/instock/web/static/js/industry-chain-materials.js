(function () {
    'use strict';
    window.InStockChainMaterials = function ({bridge, onChange}) {
        const el = id => document.getElementById(`chain-material-${id}`);
        const root = el('panel'), status = el('status'), bookSelect = el('book'), sourceSelect = el('source'), rowSelect = el('row');
        const disclosure = el('date'), confirm = el('confirm'), preview = el('preview');
        const query = new URLSearchParams(location.search);
        let handoff = query.get('sourceModule') === 'industry-prosperity' ? query : null;
        let books = [], revision = 0, request = 0, controller = null, loadedScope = '', busy = false, loading = false;
        const scope = () => JSON.stringify([bridge?.config?.user?.id, bridge?.config?.workspace?.id,
            bridge?.config?.instanceId, bridge?.config?.modId, bridge?.config?.gateways?.data,
            bridge?.config?.session?.id, bridge?.config?.grants?.permissions?.includes('analysis.read')]);
        let hostScope = scope();
        const text = (tag, value) => { const item = document.createElement(tag); item.textContent = value; return item; };
        const selectedBook = () => books.find(book => book.id === bookSelect.value);
        const selectedSource = () => selectedBook()?.sourceMaterials.find(source => source.id === sourceSelect.value);
        const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
        function sourceUrl(source) {
            try { const url = new URL(source.url); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch (_) { return null; }
        }
        function usable(book, source) {
            const g = source.businessRevenue;
            return book.mode === 'reported' && book.fiscalPeriod?.basis === 'annual' && validDate(book.fiscalPeriod.periodEnd)
                && source.kind === 'filing' && ['available', 'verified'].includes(source.status) && source.basis === 'annual'
                && source.periodEnd === book.fiscalPeriod.periodEnd && g?.contentOrigin === 'pdf-text'
                && g.scope === 'main-business' && g.currency === 'CNY' && book.security?.currency === 'CNY' && g.unit === '亿元'
                && ['industry', 'product', 'region', 'channel'].includes(g.dimension) && g.title && g.columnHeader
                && g.confirmedAt && Number.isFinite(Date.parse(g.confirmedAt))
                && Number.isInteger(g.pdfPage) && g.pdfPage > 0 && Number.isInteger(g.pdfPageCount) && g.pdfPage <= g.pdfPageCount
                && Array.isArray(g.rows) && g.rows.length > 0 && g.rows.length <= 40
                && g.rows.every(row => row.label && typeof row.value === 'number' && Number.isFinite(row.value)
                    && row.rawValue && ['元', '万元', '亿元'].includes(row.rawUnit) && row.excerpt)
                && new Set(g.rows.map(row => row.label)).size === g.rows.length && sourceUrl(source);
        }
        function options(select, rows, placeholder) {
            select.replaceChildren(new Option(placeholder, ''), ...rows.map(([id, label]) => new Option(label, id)));
        }
        function controls() {
            root.querySelectorAll('button, select, input').forEach(item => { item.disabled = busy || loading; });
        }
        function changed() { confirm.checked = false; onChange(); }
        function clear(message = '材料已移除；未修改财报原件。') {
            request += 1; controller?.abort(); loading = false;
            books = []; revision = 0; loadedScope = ''; disclosure.value = ''; confirm.checked = false;
            options(bookSelect, [], '请选择底稿'); options(sourceSelect, [], '请选择原表'); options(rowSelect, [], '请选择业务项目');
            preview.replaceChildren(); status.textContent = message; controls(); onChange();
        }
        function drawRow() {
            changed(); preview.replaceChildren();
            const book = selectedBook(), source = selectedSource(), group = source?.businessRevenue;
            const row = group?.rows.find(item => item.label === rowSelect.value);
            if (!book || !source || !row) return;
            preview.append(text('strong', `${book.security.name} · ${book.security.symbol} · ${book.fiscalPeriod.periodEnd} · ${group.title}`),
                text('p', `${row.label}：${row.rawValue} ${row.rawUnit}（归一化 ${row.value} 亿元）· CNY · PDF 第 ${group.pdfPage} 页`),
                text('p', `已采用项目 ${group.rows.length} 项；未可靠识别 ${group.skippedRows} 行。仅当前表维度，不代表公司全部收入。`),
                text('pre', `${group.columnHeader}\n${row.excerpt}`));
            const link = text('a', '打开财报原页 ↗'); const url = new URL(sourceUrl(source)); url.hash = `page=${group.pdfPage}`;
            link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; preview.append(link);
        }
        function chooseSource() {
            disclosure.value = ''; changed();
            const group = selectedSource()?.businessRevenue;
            options(rowSelect, (group?.rows || []).map(row => [row.label, row.label]), '请选择业务项目，不自动推断关系');
            preview.replaceChildren();
        }
        function chooseBook() {
            changed(); disclosure.value = '';
            const book = selectedBook();
            options(sourceSelect, (book?.sourceMaterials || []).filter(source => usable(book, source)).map(source => [source.id, source.label]), '请选择已采用主营原表');
            chooseSource();
            if (book && sourceSelect.options.length === 1) status.textContent = '此底稿没有期间、原文、币种与来源完整的已采用主营表；请先回财报研究补齐。';
        }
        async function read() {
            if (busy || loading) return;
            clear('正在读取当前工作区财报…'); loading = true; controls();
            const token = request; controller = new AbortController();
            try {
                if (bridge?.whenReady) await bridge.whenReady();
                if (token !== request) return;
                const config = bridge?.config;
                const initialScope = scope();
                if (!config?.session?.accessToken || !config.instanceId || !config.grants?.permissions?.includes('analysis.read') || !config.gateways?.data) throw new Error('请从已授权的 Desk 打开；独立页不能读取工作区私有底稿。');
                if (handoff && (handoff.get('sourceUserId') !== config.user.id || handoff.get('sourceWorkspaceId') !== config.workspace.id)) throw new Error('交接来源与当前工作区或用户不同。请切回原工作区，或移除交接后重新选择。');
                const url = new URL('/api/research-archive/industry-inputs', config.gateways.data);
                const response = await fetch(url.href, {signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]), cache: 'no-store',
                    headers: {Authorization: `Bearer ${config.session.accessToken}`, 'X-Newma-Desk-Instance-Id': config.instanceId}});
                if (!response.ok) throw new Error('财报底稿读取失败，请重试。');
                const data = await response.json();
                if (token !== request || initialScope !== scope()) return;
                if (!Number.isInteger(data?.revision) || data.revision < 0 || !Array.isArray(data.workbooks)
                    || data.workbooks.some(book => !book || typeof book.id !== 'string' || !book.security || !book.fiscalPeriod
                        || !Array.isArray(book.sourceMaterials))) throw new Error('财报底稿格式异常，未采用任何材料。');
                books = data.workbooks; revision = data.revision; loadedScope = initialScope;
                options(bookSelect, books.map(book => [book.id, `${book.security.name} · ${book.security.symbol} · ${book.fiscalPeriod.periodEnd || '期间待确认'}`]), '请选择底稿');
                status.textContent = books.length ? '读取完成；请选择原表项目，再核对披露日期。保存日和财报截止日不是披露日。' : '当前工作区暂无财报底稿。';
                if (handoff) {
                    bookSelect.value = handoff.get('sourceWorkbookId') || ''; chooseBook();
                    const book = selectedBook();
                    if (!book) throw new Error('交接底稿已移除或当前工作区不存在；未改用其他公司。');
                    sourceSelect.value = handoff.get('sourceId') || ''; chooseSource();
                    if (!selectedSource()) throw new Error('交接原表已移除或不再满足采用条件；请回财报研究核对。');
                    if (book.updatedAt !== handoff.get('sourceUpdatedAt')) status.textContent = '底稿在交接后已更新，以下是当前版本；需重新核对原页和披露日期。';
                }
            } catch (error) {
                if (token === request) clear(error.message || '读取失败');
            } finally { if (token === request) { loading = false; controls(); } }
        }
        function material(asOf, market) {
            if (!selectedBook()) return null;
            if (loadedScope !== scope()) throw new Error('工作区已变化，请重新读取材料。');
            const book = selectedBook(), source = selectedSource(), group = source?.businessRevenue;
            const row = group?.rows.find(item => item.label === rowSelect.value);
            if (!source || !row || !usable(book, source)) throw new Error('请选择已采用原表和业务项目。');
            if (!confirm.checked) throw new Error('请先核对原页与披露日期，再确认材料。');
            const date = disclosure.value;
            if (!validDate(date) || date < book.fiscalPeriod.periodEnd || date > new Date().toISOString().slice(0, 10) || (asOf && date > asOf)) throw new Error('披露日期须真实有效，不能早于报告期末、晚于今天或研究截止日。');
            if (market && market !== 'GLOBAL' && book.security.market !== market) throw new Error('财报所属市场与研究市场不一致，请核对。');
            return {workbookId: book.id, sourceId: source.id, workbookUpdatedAt: book.updatedAt, sourceRevision: revision,
                security: book.security, periodEnd: book.fiscalPeriod.periodEnd, basis: 'annual', dimension: group.dimension,
                title: group.title, pdfPage: group.pdfPage, columnHeader: group.columnHeader, row, currency: 'CNY',
                sourceUrl: preview.querySelector('a').href, disclosureDate: date, disclosureDateOrigin: 'user-confirmed',
                boundary: '仅为已采用财报业务事实，不证明上下游关系、供应商集中度、依赖比例或价格弹性。'};
        }
        function context(asOf, market) {
            try { const value = material(asOf, market); return value ? {status: 'confirmed', material: value} : {status: loading ? 'loading' : 'empty'}; }
            catch (error) { return {status: 'needs-review', reason: error.message}; }
        }
        function evidence(value) {
            if (!value) return null;
            const claim = `${value.security.name}（${value.security.symbol}），${value.periodEnd}年度主营业务，${value.title}：${value.row.label}收入${value.row.rawValue}${value.row.rawUnit}（${value.row.value}亿元，CNY），PDF物理第${value.pdfPage}页。仅业务收入事实，不证明供需关系或依赖比例。`;
            if (claim.length > 800 || value.sourceUrl.length > 500) throw new Error('材料引用超过研究包长度限制，请在财报研究整理来源后重试。');
            return {id: 'desk-main-business', claim, source_type: 'user-adopted-filing-row', source_ref: value.sourceUrl,
                strength: 'unverified', observed_at: value.disclosureDate};
        }
        el('load').addEventListener('click', () => void read());
        el('clear').addEventListener('click', () => { handoff = null; clear(); });
        bookSelect.addEventListener('change', chooseBook); sourceSelect.addEventListener('change', chooseSource); rowSelect.addEventListener('change', drawRow);
        disclosure.addEventListener('input', changed); confirm.addEventListener('change', onChange);
        document.addEventListener('vibedesk:init', () => {
            const next = scope(); if (next !== hostScope) { hostScope = next; clear('工作区身份已变化，请重新读取材料。'); }
        });
        status.textContent = handoff ? '收到行业景气交接标识，点击读取当前工作区原件；不会直接使用网址作为证据。' : '可读取当前工作区已采用的财报主营表；不修改原件。';
        return {read, context, material, evidence, setBusy(value) { busy = value; controls(); }, clear() { handoff = null; clear(); }};
    };
})();
