(function () {
    'use strict';
    const bridge = window.InStockNewmaDesk || window.InStockVibeDesk;
    const actionId = 'analysis.research-book';
    const byId = id => document.getElementById(id);
    const text = (id, value) => { byId(id).textContent = value; };
    const draft = [];
    const reviewPanels = [];
    const originPanels = [];
    const prefix = 'instock.research-book.draft.v2:';
    const symbolPattern = /^\d{6}(?:\.(?:SH|SZ|BJ))?$/;
    let storageKey = null, initialized = false, editingIndex = -1;
    let result = null, editVersion = 0, analysisVersion = 0;
    let checking = false, checkError = null;
    let editorOrigin = null, editorOriginSymbol = '';
    const today = () => new Date().toISOString().slice(0, 10);
    const lines = value => String(value || '').split(/\r?\n/).map(item => item.trim()).filter(Boolean);
    const ids = value => String(value || '').split(/[\n,，]+/).map(item => item.trim()).filter(Boolean);
    const fields = {symbol: 'book-symbol', name: 'book-stock-name', sector: 'book-sector',
        target_weight_pct: 'book-weight-input', thesis: 'book-thesis', invalidation: 'book-invalidation',
        risk_tags: 'book-risks', snapshot_ids: 'book-snapshots'};

    function scopeKey() {
        if (!bridge?.embedded) return prefix + 'standalone';
        const config = bridge.config;
        return config?.user?.id && config?.workspace?.id
            ? prefix + JSON.stringify([config.user.id, config.workspace.id]) : null;
    }
    function showError(error) {
        text('book-alert', error.message || String(error));
        byId('book-alert').style.display = 'block';
    }
    function saveDraft() {
        if (!storageKey || storageKey !== scopeKey()) return;
        try {
            localStorage.setItem(storageKey, JSON.stringify({name: byId('book-name').value.trim(),
                asOf: byId('book-date').value, items: draft}));
            text('book-draft-state', bridge?.embedded ? '已保存到当前工作区本机草稿' : '已保存独立模式本机草稿');
        } catch (_) { text('book-draft-state', '本机保存不可用，请勿关闭页面'); }
    }
    function restoreDraft() {
        try {
            const payload = JSON.parse(localStorage.getItem(storageKey) || 'null');
            if (!payload) {
                text('book-draft-state', localStorage.getItem('instock.research-book.draft.v1')
                    ? '旧草稿仍保留，归属不明，未自动载入' : '当前范围暂无草稿');
                return;
            }
            if (!Array.isArray(payload.items) || payload.items.length > 100 || payload.items.some(item =>
                !item || item.market !== 'CN' || !symbolPattern.test(item.symbol) || !item.name || !item.sector || !item.thesis ||
                !['invalidation', 'risk_tags', 'snapshot_ids'].every(key => Array.isArray(item[key]) && item[key].every(value => typeof value === 'string')))) {
                throw new Error('草稿格式无效');
            }
            draft.push(...payload.items);
            if (typeof payload.name === 'string') byId('book-name').value = payload.name;
            if (/^\d{4}-\d{2}-\d{2}$/.test(payload.asOf)) byId('book-date').value = payload.asOf;
            text('book-draft-state', '已恢复当前范围的本机草稿');
        } catch (_) { text('book-draft-state', '草稿恢复失败，原记录未改动'); }
    }
    function fillEditor(item) {
        editorOrigin = item.research_origin || null;
        editorOriginSymbol = item.symbol || '';
        Object.entries(fields).forEach(([key, id]) => {
            const value = item[key];
            byId(id).value = Array.isArray(value) ? value.join(key === 'snapshot_ids' ? ',' : '\n') : value ?? '';
        });
    }
    function resetEditor() {
        editVersion += 1;
        editingIndex = -1;
        fillEditor({target_weight_pct: 0});
        text('book-add', '加入组合');
        byId('book-cancel').hidden = true;
    }
    function editItem(index) {
        editVersion += 1;
        editingIndex = index;
        fillEditor(draft[index]);
        text('book-add', '保存修改');
        byId('book-cancel').hidden = false;
        byId('book-symbol').focus();
        publish();
    }
    function invalidateResult() {
        analysisVersion += 1;
        checking = false; checkError = null;
        disposeReviews();
        result = null;
        ['book-items', 'book-weight', 'book-cash', 'book-missing'].forEach(id => text(id, '--'));
        byId('book-list').replaceChildren(element('div', draft.length ? '组合已修改，请重新检查' : '检查组合后显示集中度与引用状态', 'book-empty'));
        text('book-meta', '引用匹配不等于投资主张已验证；人工复核按当前运行模式单独读取，不混用本机与工作区记录。');
        text('book-review-summary', '人工复核尚未读取，不代表没有风险。');
        text('book-thesis-summary', '尚未检查研究复核事项，旧结论已撤下。');
        byId('book-review-agenda').replaceChildren();
        byId('book-run').disabled = !storageKey;
        text('book-run', '检查组合');
    }
    function syncScope() {
        const next = scopeKey();
        if (initialized && next === storageKey) return;
        const first = !initialized;
        initialized = Boolean(next);
        storageKey = next;
        draft.length = 0;
        resetEditor();
        byId('book-name').value = '核心观察组合';
        byId('book-date').value = today();
        byId('book-alert').style.display = 'none';
        text('book-handoff', first ? '' : '工作区已切换，旧编辑内容和检查结果已撤下。');
        document.querySelectorAll('.book-input input, .book-input textarea, .book-input button').forEach(control => { control.disabled = !next; });
        if (next) restoreDraft();
        else text('book-draft-state', '等待 Desk 工作区身份，尚未读取或保存草稿');
        invalidateResult(); renderDraft(); publish();
        if (first && next) void applyUrlPrefill();
    }
    async function applyUrlPrefill() {
        const query = new URLSearchParams(location.search);
        const symbol = (query.get('symbol') || '').trim().toUpperCase();
        if (!symbol && !query.has('sourceSnapshotId')) return;
        const version = editVersion, scope = storageKey;
        const current = () => version === editVersion && scope === storageKey && scope === scopeKey();
        try {
            if ((query.get('market') || 'CN').toUpperCase() !== 'CN' || !symbolPattern.test(symbol)) {
                throw new Error('当前编辑器仅支持 A 股；请核对市场和 6 位代码，不会自动截断或改换证券。');
            }
            if (query.has('sourceSnapshotId')) {
                text('book-handoff', '正在读取公司档案的完整研究结论…');
                const response = await bridge.fetchAnalysis('/api/v1/research-books?' + new URLSearchParams({symbol,
                    market: 'CN', sourceSnapshotId: query.get('sourceSnapshotId')}));
                const payload = await response.json();
                if (!current()) return;
                if (!response.ok || !payload.ok) throw new Error(payload.error?.message || '公司档案交接读取失败');
                fillEditor(payload.data.item);
                if (query.has('researchOriginId')) {
                    const reference = {researchOriginId: query.get('researchOriginId'), originUserId: query.get('originUserId'),
                        originWorkspaceId: query.get('originWorkspaceId'), snapshotId: query.get('researchOriginSnapshotId')};
                    if (!/^[a-f0-9]{32}$/.test(reference.researchOriginId) || !payload.data.item.snapshot_ids.includes(reference.snapshotId)
                        || reference.originUserId !== bridge?.config?.user?.id || reference.originWorkspaceId !== bridge?.config?.workspace?.id) {
                        throw new Error('研究起点与当前工作区或来源引用不符，未携带；公司草稿仍需手动核对。');
                    }
                    editorOrigin = reference;
                }
                if (!draft.length) byId('book-date').value = payload.data.as_of;
                text('book-handoff', `${payload.data.boundary} 来源截止日 ${payload.data.as_of}。${draft.length ? '已有组合的截止日保持不变。' : ''}`);
                if (editorOrigin) text('book-handoff', byId('book-handoff').textContent + ' 已附带私有研究起点标识，加入并检查后可单独读取原文。');
            } else {
                // Compatibility for old links: preserve text, never silently shorten risk conditions.
                fillEditor({symbol, name: query.get('name'), sector: query.get('sector') || query.get('industry'),
                    thesis: query.get('thesis'), invalidation: lines(query.get('invalidation')),
                    risk_tags: lines(query.get('risks')), snapshot_ids: ids(query.get('snapshotIds')), target_weight_pct: 0});
                text('book-handoff', '旧链接内容仅作未核验草稿，请补全行业、理由和证伪条件后主动加入。');
            }
            publish();
        } catch (error) { if (current()) { text('book-handoff', '交接未完成，请返回公司档案重新生成。'); showError(error); } }
    }
    function inputItem() {
        const symbol = byId('book-symbol').value.trim().toUpperCase();
        const name = byId('book-stock-name').value.trim(), sector = byId('book-sector').value.trim();
        const weight = Number(byId('book-weight-input').value), thesis = byId('book-thesis').value.trim();
        const invalidation = lines(byId('book-invalidation').value);
        if (!symbolPattern.test(symbol)) throw new Error('请输入 6 位 A 股代码，可带 .SH、.SZ 或 .BJ 后缀');
        if (!name || !sector || !thesis) throw new Error('请补全股票名称、行业和跟踪理由');
        if (!Number.isFinite(weight) || weight < 0 || weight > 100) throw new Error('研究权重必须在 0% 到 100% 之间');
        if (!invalidation.length) throw new Error('至少填写一个证伪条件');
        const item = {symbol, name, market: 'CN', sector, target_weight_pct: weight, thesis, invalidation,
            risk_tags: lines(byId('book-risks').value), snapshot_ids: ids(byId('book-snapshots').value)};
        if (editorOrigin && symbol === editorOriginSymbol && item.snapshot_ids.includes(editorOrigin.snapshotId)) item.research_origin = {...editorOrigin};
        return item;
    }
    function packet() {
        const name = byId('book-name').value.trim(), asOf = byId('book-date').value;
        if (!name || !asOf) throw new Error('请填写组合名称和截止日');
        if (!draft.length) throw new Error('至少加入一个观察标的');
        return {schema_version: 'instock-research-book-packet-v1', name, as_of: asOf, items: JSON.parse(JSON.stringify(draft))};
    }
    function element(tag, value, className) {
        const node = document.createElement(tag); node.textContent = value;
        if (className) node.className = className;
        return node;
    }
    function renderDraft() {
        const root = byId('book-draft'); root.replaceChildren();
        text('book-draft-count', `${draft.length} 个观察标的`);
        draft.forEach((item, index) => {
            const row = element('div', '', 'book-draft-item'), body = element('div', '');
            body.append(element('b', `${item.name} · ${item.symbol} · ${item.target_weight_pct}%`), element('p', `${item.sector} · ${item.thesis}`));
            if (item.research_origin) body.append(element('p', '已关联私有研究起点，检查后可单独读取；未保存原文到本机草稿。'));
            const actions = element('div', ''), edit = element('button', '编辑', 'book-add'), remove = element('button', '移除', 'book-remove');
            edit.type = remove.type = 'button';
            edit.addEventListener('click', () => editItem(index));
            remove.addEventListener('click', () => {
                draft.splice(index, 1); resetEditor(); invalidateResult(); saveDraft(); renderDraft(); publish();
            });
            actions.append(edit, remove); row.append(body, actions); root.append(row);
        });
    }
    async function request(input) {
        if (bridge?.canInvokeAction?.(actionId)) return bridge.invokeAction(actionId, input);
        if (bridge?.embedded) throw new Error('Desk 检查能力尚未就绪，请重新加载模组');
        const response = await bridge.fetchAnalysis('/api/v1/research-books', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input)});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message || '研究组合检查失败');
        return payload;
    }
    const coverageLabel = state => ({complete: '引用已匹配', missing: '引用未全部匹配', none: '未关联引用'})[state] || '引用状态未知';
    const stateLabel = state => ({resolved: '证券、市场、截止日已匹配', missing: '不存在或已过期',
        date_unknown: '缺少有效截止日', after_cutoff: '晚于组合截止日', scope_unverified: '不能确认证券范围',
        market_mismatch: '市场不一致', security_mismatch: '证券不一致', scope_ambiguous: '同一证券暴露不唯一'})[state] || '状态未知';
    const reviewReason = reason => ({
        reference_unavailable: `引用不可用于对照：${stateLabel(reason.reference_state)}`,
        source_incomplete: '来源数据覆盖不完整',
        research_details_incomplete: '公司来源研究字段不完整，须重新生成',
        thesis_text_differs: '观察理由与来源结论文字不同，需核对含义',
        invalidation_not_carried: `来源证伪条件未按原文带入：${(reason.conditions || []).join('；')}`,
        periodic_review_due: `来源距组合截止日 ${reason.calendar_age_days} 个自然日，达到90日复核提醒（不代表失效）`,
        no_comparable_dossier: '没有完整且匹配的公司研究结论可供对照',
    })[reason.code] || '需核对来源';
    function renderThesisReview(card, item) {
        const review = item.thesis_review;
        const panel = element('section', '', 'book-thesis-review');
        panel.append(element('h3', !review ? '旧记录未检查研究差异，请重新检查' : review.state === 'needs_review' ? '研究理由待复核' : '文字已对齐，证伪仍未验证'));
        if (review) {
            const reasons = element('ul', '');
            review.reasons.forEach(reason => reasons.append(element('li', reviewReason(reason) + (reason.as_of ? ` · 来源截止 ${reason.as_of}` : ''))));
            panel.append(reasons);
            review.comparisons.forEach(comparison => {
                const detail = element('details', '', 'book-reference');
                detail.append(element('summary', `对照 ${comparison.as_of} 公司来源 · 相隔 ${comparison.calendar_age_days} 天`),
                    element('p', `当前观察理由：${item.thesis}`), element('p', `来源结论：${comparison.source_conclusion}`),
                    element('p', `来源证伪条件：${comparison.source_invalidation.join('；')}`), element('p', comparison.snapshot_id));
                panel.append(detail);
            });
            panel.append(element('p', review.boundary));
        }
        card.append(panel);
    }
    function renderReviewAgenda() {
        const root = byId('book-review-agenda'); root.replaceChildren();
        const summary = result.review_summary;
        if (!summary) {
            text('book-thesis-summary', '旧结果未生成研究复核清单，请重新检查；不追认为研究逻辑已验证。');
            return;
        }
        text('book-thesis-summary', `待复核 ${summary.items_to_review}/${result.items.length} 项，涉及研究权重 ${summary.review_target_weight_pct}%；其中无完整公司对照 ${summary.without_comparable_dossier} 项。文字对齐 ${summary.text_aligned_items} 项也不代表逻辑成立。按研究权重排序，零权重观察项仍保留；90自然日仅作复核提醒，按组合截止日而非今天计算。`);
        result.items.map((item, index) => ({item, index})).filter(({item}) => item.thesis_review?.state === 'needs_review')
            .sort((a, b) => b.item.target_weight_pct - a.item.target_weight_pct || a.index - b.index)
            .forEach(({item, index}) => {
                const labels = {reference_unavailable: '引用不可用', source_incomplete: '来源覆盖不足',
                    research_details_incomplete: '旧研究字段缺失', thesis_text_differs: '理由文字不同',
                    invalidation_not_carried: '证伪条件待核对', periodic_review_due: '90日复核提醒',
                    no_comparable_dossier: '缺公司对照'};
                const reasons = [...new Set(item.thesis_review.reasons.map(reason => labels[reason.code] || '需核对来源'))];
                const button = element('button', `${item.name} · ${item.symbol} · ${item.target_weight_pct}%：${reasons.join('；')}`);
                button.type = 'button';
                button.addEventListener('click', () => {
                    const card = byId(`book-result-${index}`);
                    card.scrollIntoView({block: 'start'}); card.focus({preventScroll: true});
                });
                root.append(button);
            });
    }
    function disposeReviews() {
        reviewPanels.forEach(panel => panel.reader.dispose());
        reviewPanels.length = 0;
        originPanels.forEach(panel => panel.reader.dispose());
        originPanels.length = 0;
        byId('book-review-refresh').hidden = true;
    }
    function reviewContext() {
        return reviewPanels.map(panel => ({symbol: panel.symbol, market: panel.market,
            snapshotId: panel.snapshotId, ...panel.reader.context()}));
    }
    function reviewsChanged() {
        if (!result) return;
        const reviews = reviewContext();
        const rows = reviews.flatMap(review => review.relations);
        const count = status => rows.filter(row => row.status === status).length;
        const loaded = reviews.filter(review => review.status === 'ready').length;
        const missing = result.items.filter(item => !item.snapshot_references.some(ref => ref.review_context)).length;
        const reviewScope = bridge?.embedded === false ? '本浏览器人工复核（不同步到 Desk）' : '工作区人工复核';
        text('book-review-summary', `${reviewScope}：已读取 ${loaded}/${reviews.length} 条产业链来源；存在反证 ${count('contradicted')} 条，证据不足 ${count('insufficient')} 条，旧意见待复核 ${count('needs-review')} 条，尚无人工意见 ${count('not-reviewed')} 条。${reviews.length - loaded} 条来源未读或不可用；${missing} 个观察项缺少可用直接关系。未知不代表无风险，当前人工意见不是截止日当时的历史回放。`);
        publish();
    }
    async function refreshReviews() {
        const version = analysisVersion;
        byId('book-review-refresh').disabled = true;
        try {
            // Reuse the source reader, sequentially, without flooding shared storage for a large book.
            for (const panel of [...reviewPanels]) {
                if (version !== analysisVersion) return;
                await panel.reader.refresh();
                if (version === analysisVersion) reviewsChanged();
            }
        } finally { if (version === analysisVersion) byId('book-review-refresh').disabled = false; }
    }
    function render(payload) {
        const data = payload?.ok === true ? payload.data : payload;
        if (data?.engine?.name !== 'instock-research-book') throw new Error('返回结果缺少研究组合引擎标识');
        disposeReviews(); result = data;
        text('book-items', data.summary.items);
        text('book-weight', `${Number(data.summary.total_target_weight_pct).toFixed(1)}%`);
        text('book-cash', `${Number(data.summary.cash_weight_pct).toFixed(1)}%`);
        text('book-missing', data.items.filter(item => item.snapshot_coverage !== 'complete' || item.snapshot_references.some(ref => ref.source_coverage !== 'complete')).length);
        const root = byId('book-list'); root.replaceChildren();
        data.items.forEach((item, index) => {
            const card = element('section', '', 'book-item'), head = element('div', '', 'book-head');
            card.id = `book-result-${index}`; card.tabIndex = -1;
            head.append(element('b', `${item.name} · ${item.symbol}`), element('strong', `${item.target_weight_pct}%`));
            card.append(head, element('p', item.thesis), element('p', `证伪：${item.invalidation.join('；')}`));
            const tags = element('div', '', 'book-tags');
            [item.sector, coverageLabel(item.snapshot_coverage)].forEach(value => tags.append(element('span', value)));
            card.append(tags);
            renderThesisReview(card, item);
            item.risk_tags.forEach(value => card.append(element('p', value)));
            item.snapshot_references.forEach(ref => {
                const detail = element('details', '', 'book-reference');
                detail.append(element('summary', `${ref.analysis?.name || '引用'} · ${stateLabel(ref.state)}`),
                    element('p', `${ref.snapshot_id} · 截止日 ${ref.as_of || '未知'} · 来源覆盖 ${ref.source_coverage === 'complete' ? '完整' : ref.source_coverage === 'partial' ? '部分' : '未知'}`));
                if (ref.state !== 'missing') detail.append(element('p', `来源生成于 ${ref.source_generated_at || '旧记录未提供'}。读取的是原分析，不代表当前行情；新鲜度按原分析时点记录。`));
                if (ref.research) {
                    detail.append(element('p', `来源结论：${ref.research.conclusion || '旧快照未提供'}`));
                    [['tensions', '张力'], ['gaps', '证据缺口'], ['invalidation_conditions', '来源证伪条件']].forEach(([key, label]) => {
                        (ref.research[key] || []).forEach(value => detail.append(element('p', `${label}：${value}`)));
                    });
                    if (!ref.research_details_complete) detail.append(element('p', '旧快照缺少完整研究字段，请回公司档案重新生成。'));
                }
                card.append(detail);
                if (ref.state === 'resolved' && ref.review_context) {
                    const reviews = element('section', '', 'book-workspace-reviews');
                    card.append(reviews);
                    const reader = window.InStockStockChainReviews({bridge, onChange: reviewsChanged,
                        root: reviews, autoLoad: false, title: `人工复核 · ${ref.review_context.research_context.theme} · 来源 ${ref.as_of}`});
                    reviewPanels.push({symbol: item.symbol, market: item.market, snapshotId: ref.snapshot_id, reader});
                    reader.setData(ref.review_context);
                }
            });
            if (!item.snapshot_references.some(ref => ref.review_context)) {
                card.append(element('p', '没有可用的产业链直接关系，人工复核覆盖未知；请补关联来源，不能据此认为无风险。'));
            }
            if (item.research_origin) {
                const ref = item.snapshot_references.find(ref => ref.snapshot_id === item.research_origin.snapshotId);
                if (ref?.state === 'resolved' && ref.review_context) {
                    const root = element('section', '', 'book-workspace-reviews book-research-origin'); card.append(root);
                    const reader = window.InStockResearchOrigin({bridge, root, mode: 'read', onChange: publish, reference: item.research_origin});
                    reader.setData(ref.review_context);
                    originPanels.push({symbol: item.symbol, snapshotId: ref.snapshot_id, reader});
                } else card.append(element('p', '研究起点关联尚未匹配有效的产业链直接关系，未读取原文；请返回公司档案核对来源。'));
            }
            root.append(card);
        });
        const warnings = data.warnings.map(value => {
            const [kind, name] = value.split(':');
            return ({position_concentration: '单一标的研究权重偏高', sector_concentration: '行业研究权重偏高',
                snapshot_coverage: '引用未全部匹配', source_incomplete: '引用来源数据不完整'})[kind] + '：' + name;
        });
        text('book-meta', `${data.as_of} · ${warnings.join('；') || '未发现集中度或引用匹配警告'}。引用匹配不等于投资主张已验证；人工复核独立读取，不改研究权重，不写入共享快照或本机草稿。`);
        byId('book-review-refresh').hidden = !reviewPanels.length;
        renderReviewAgenda();
        reviewsChanged();
        void refreshReviews();
    }
    function context() {
        if (storageKey !== scopeKey()) syncScope();
        const editor = Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, byId(id).value]));
        Object.assign(editor, {mode: editingIndex >= 0 ? 'editing' : 'new', index: editingIndex >= 0 ? editingIndex : null,
            researchOrigin: editorOrigin, boundary: '编辑内容尚未加入或保存到组合；检查仅使用已加入的草稿。'});
        const visibleDraft = {draftItems: draft, editor, editorNotAdded: true,
            status: !storageKey ? 'awaiting-workspace' : checking ? 'running' : checkError ? 'error' : result ? 'checked' : 'unchecked',
            error: checkError};
        return {view: {id: 'research-book', title: '研究组合'},
            filters: {name: byId('book-name').value.trim(), asOf: byId('book-date').value},
            visibleBlocks: [{id: 'positions', type: 'research-book', title: '研究观察项与引用核验'}],
            data: result ? {...visibleDraft, name: result.name, asOf: result.as_of, summary: result.summary, items: result.items,
                exposures: result.exposures, warnings: result.warnings, limitations: result.limitations, snapshot: result.snapshot,
                thesisReview: result.review_summary || null,
                thesisReviewState: result.review_summary ? 'source_text_comparison_only' : 'legacy_requires_recheck',
                relationshipReviews: reviewContext(), researchOrigins: originPanels.map(panel => ({symbol: panel.symbol,
                    snapshotId: panel.snapshotId, ...panel.reader.context()}))}
                : visibleDraft,
            actions: [{id: actionId, label: '检查研究组合', available: Boolean(storageKey && !checking && bridge?.canInvokeAction?.(actionId))}]};
    }
    function publish() { bridge?.setContextProvider?.(context); bridge?.publishContext?.(); }
    byId('book-add').addEventListener('click', () => {
        byId('book-alert').style.display = 'none';
        try {
            if (!storageKey || storageKey !== scopeKey()) throw new Error('等待当前工作区身份');
            const item = inputItem();
            if (editingIndex >= 0) draft[editingIndex] = item;
            else { if (draft.length >= 100) throw new Error('最多支持 100 个观察标的'); draft.push(item); }
            resetEditor(); text('book-handoff', '已加入当前范围的本机草稿，尚未检查。');
            invalidateResult(); saveDraft(); renderDraft(); publish();
        } catch (error) { showError(error); }
    });
    byId('book-cancel').addEventListener('click', () => { resetEditor(); publish(); });
    byId('book-review-refresh').addEventListener('click', () => void refreshReviews());
    async function checkCurrentBook() {
        if (byId('book-run').disabled) throw new Error('当前组合仍在检查，请等待原任务完成');
        invalidateResult();
        const version = analysisVersion, scope = storageKey;
        const current = () => version === analysisVersion && scope === storageKey && scope === scopeKey();
        byId('book-alert').style.display = 'none'; byId('book-run').disabled = true; text('book-run', '检查中…');
        checking = true; publish();
        try {
            const response = await request(packet());
            if (current()) {
                render(response);
                text('book-handoff', '已完成当前草稿检查；研究文字对照不代表证伪条件已经验证。');
                window.InStockAnalysisHistory?.rendered('latest');
            } else throw new Error('组合或工作区已变化，未采用旧检查结果');
            return {name: result.name, asOf: result.as_of, summary: result.summary};
        } catch (error) { if (current()) { checkError = error.message || String(error); showError(error); } throw error; }
        finally { if (current()) { checking = false; byId('book-run').disabled = false; text('book-run', '检查组合'); publish(); } }
    }
    byId('book-run').addEventListener('click', () => { void checkCurrentBook().catch(() => {}); });
    bridge?.setUiActionHandler?.((id, input) => {
        if (id !== actionId) throw new Error('当前页面未注册该操作');
        if (Object.keys(input || {}).length) throw new Error('页面检查只使用当前可见草稿，请先在页面修改，不接受隐藏输入覆盖');
        return checkCurrentBook();
    });
    document.querySelectorAll('.book-input input, .book-input textarea').forEach(control => {
        control.addEventListener('input', () => {
            if (byId('book-handoff').textContent === '正在读取公司档案的完整研究结论…') {
                text('book-handoff', '已开始手动编辑，迟到的公司档案不会覆盖；尚未加入组合。');
            }
            editVersion += 1; invalidateResult();
            if (['book-symbol', 'book-snapshots'].includes(control.id) && editorOrigin) {
                editorOrigin = null;
                text('book-handoff', '证券或来源已编辑，旧研究起点关联已撤下；不会沿用旧原文。');
            }
            if (['book-name', 'book-date'].includes(control.id)) saveDraft();
            publish();
        });
    });
    bridge?.subscribe?.(envelope => {
        if (!storageKey || envelope.event !== 'security.selected' || envelope.source === 'instock-research-book') return;
        const value = envelope.payload || {}, symbol = String(value.symbol || value.code || '').trim().toUpperCase();
        const assetType = String(value.assetType || '').toLowerCase();
        if ((value.market && value.market !== 'CN') || !symbolPattern.test(symbol)
            || (assetType && !['stock', 'equity'].includes(assetType))) return;
        invalidateResult();
        resetEditor(); fillEditor({symbol, name: value.name, sector: value.industry || value.sector,
            snapshot_ids: value.snapshotId ? [value.snapshotId] : [], target_weight_pct: 0});
        text('book-handoff', '已选择新证券，请补全研究理由；未沿用上一证券的判断。');
        publish();
    });
    document.addEventListener('vibedesk:init', syncScope);
    document.addEventListener('instock:history-selected', event => {
        if (event.detail?.module_id !== 'research-book' || storageKey !== scopeKey()) return;
        invalidateResult();
        render(event.detail.payload);
        text('book-handoff', '正在查看已保存的检查结果，左侧本机草稿未被替换；人工复核按当前运行模式另读最新意见。');
    });
    syncScope();
})();
