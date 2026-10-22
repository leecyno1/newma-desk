(function () {
    'use strict';
    const contract = window.InStockChainReviewContract;
    const labels = {supported: '有直接支持', contradicted: '存在反证', insufficient: '证据不足',
        'needs-review': '旧意见待复核', 'not-reviewed': '尚无人工复核', unavailable: '复核读取不可用'};
    const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
    window.InStockStockChainReviews = function ({bridge, onChange, root = document.getElementById('dossier-chain-reviews'), autoLoad = true, title = '直接关系 · 人工复核'}) {
        const storage = window.InStockChainReviewStorage(bridge);
        let data = null, targets = [], records = [], archive = null, revision = 0;
        let state = 'idle', message = '', sequence = 0, controller;
        const scope = storage.scope;
        let currentScope = scope();
        const available = () => storage.info().canRead;
        function discard() {
            ++sequence; controller?.abort(); records = []; archive = null; revision = 0;
            state = 'idle'; currentScope = scope();
        }
        function relationRows() {
            return targets.map(target => {
                const record = state === 'ready' ? records.find(row => contract.sameRelation(row.target, target)) : null;
                const current = record && contract.matches(record, target, origin => archive?.status === 'ready'
                    && archive.materials.some(row => contract.archiveIdentity(row) === contract.archiveIdentity(origin)));
                return {source: target.source.id, target: target.target.id, label: `${target.source.name} → ${target.target.name}`,
                    claim: target.relation, status: state !== 'ready' ? 'unavailable' : !record ? 'not-reviewed' : current ? record.decision : 'needs-review',
                    review: record || null};
            });
        }
        function context() {
            if (scope() !== currentScope) discard();
            return {status: state, storage: storage.info(), revision, relations: relationRows(), archiveStatus: archive?.status || 'not-read',
                boundary: storage.info().description + ' 仅已保存人工意见，读取时核对证据及归档版本；是当前意见，不是历史截止日回放。不是事实认证或公司受损结论，不改评分、不写入共享档案快照。'};
        }
        function render() {
            root.replaceChildren();
            if (!data) return;
            root.append(text('h3', title));
            if (!targets.length) { root.append(text('p', '快照无可复核的直接关系，不能据此判断没有风险。')); return; }
            const load = text('button', state === 'loading' ? '读取中…' : '刷新人工复核');
            load.type = 'button'; load.className = 'dossier-review-load'; load.disabled = !available() || state === 'loading';
            load.addEventListener('click', () => void refresh()); root.append(load);
            root.append(text('p', storage.info().description));
            root.append(text('p', message || '请读取当前存储范围已保存意见；草稿和模型建议不计入。'));
            if (state !== 'ready') return;
            const rows = relationRows();
            const warnings = rows.filter(row => row.status !== 'supported');
            root.append(text('strong', warnings.length ? `需关注 ${warnings.length} / ${rows.length} 条直接关系` : '已读关系均有人工支持意见，仍非事实认证'));
            rows.forEach(row => {
                const card = document.createElement('details'); card.className = 'dossier-review-record';
                card.dataset.status = row.status; card.open = ['contradicted', 'needs-review', 'insufficient'].includes(row.status);
                card.append(text('summary', `${labels[row.status]} · ${row.label}`), text('p', row.claim));
                const record = row.review;
                if (record) {
                    card.append(text('p', `人工意见：${contract.decisions[record.decision]} · 复核时间 ${record.reviewedAt}`));
                    if (row.status === 'needs-review') card.append(text('p', '关系、日期、引用或归档版本不符，旧意见仅作历史参考，不能沿用。'));
                    if (record.archiveSource) card.append(text('p', archive?.status === 'ready' ? '已检查当前归档版本' : '归档读取不可用，此意见尚不能沿用'));
                    card.append(text('p', `资料日期 ${record.sourceDate || '未提供'} · ${record.locator || '定位未提供'}`));
                    if (record.sourceRef) {
                        const ref = text('span', record.sourceRef); let link = ref;
                        try { const url = new URL(record.sourceRef); if (['http:', 'https:'].includes(url.protocol)) {
                            link = text('a', record.sourceRef); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
                        }} catch (_) {}
                        card.append(link);
                    }
                    if (record.quote) card.append(text('blockquote', record.quote));
                    card.append(text('strong', '人工判断依据'), text('p', record.note));
                }
                root.append(card);
            });
            root.append(text('p', '只提示直接关系，不推断公司财务受损，也不自动调整评分。修改意见请回产业链复核。'));
        }
        async function refresh() {
            if (scope() !== currentScope) discard();
            if (!data || !targets.length || !available()) { render(); return; }
            controller?.abort(); controller = new AbortController();
            const operation = ++sequence, initialScope = scope();
            records = []; archive = null; revision = 0; state = 'loading'; message = '正在读取已保存人工意见并核对可用版本…';
            render(); onChange();
            try {
                const result = await storage.readRelations({theme: data.theme, market: data.market,
                    relations: targets.map(target => ({source: target.source.id, target: target.target.id}))}, {signal: controller.signal});
                const book = contract.readBook(result.book);
                if (!['ready', 'unavailable'].includes(result.archive?.status) || !Array.isArray(result.archive.materials)) throw new Error('归档版本信息不完整，请重新读取。');
                if (operation !== sequence || initialScope !== scope()) return;
                records = book.entries; archive = result.archive; revision = result.revision; state = 'ready';
                message = `已读取当前关系的最新人工意见 · ${storage.info().label}记录版本 ${revision}。来源更新后请再次刷新。`;
            } catch (error) {
                if (operation !== sequence || initialScope !== scope()) return;
                state = 'failed'; message = error.message;
            } finally { if (operation === sequence && initialScope === scope()) { render(); onChange(); } }
        }
        function setData(chain) {
            discard(); const research = chain?.research_context;
            data = research && chain.exposure ? {theme: research.theme, market: research.market, as_of: research.as_of,
                chain: research.chain, evidence: research.evidence} : null;
            targets = data ? (data.chain?.links || []).map(link => contract.targetFor(data, link)) : [];
            message = ''; render(); if (autoLoad && data && targets.length && available()) void refresh();
        }
        function onInit() {
            if (currentScope !== scope()) { discard(); message = '工作区身份变化，旧意见已撤下，请重新读取。'; render(); onChange(); }
        }
        document.addEventListener('vibedesk:init', onInit);
        return {setData, context, refresh, dispose() {
            document.removeEventListener('vibedesk:init', onInit);
            discard(); data = null; targets = []; root.replaceChildren();
        }};
    };
})();
