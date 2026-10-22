(function () {
    'use strict';
    const {decisions, day, targetFor, key, sameRelation, readBook, matches: matchesVersion} = window.InStockChainReviewContract;
    const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
    const suggestionNote = result => 'Agent 辅助建议（待人工核对）：' + result.explanation
        + (result.gaps.length ? '\n待补证据：' + result.gaps.join('；') : '');
    function assistanceState(record) {
        const assistance = record.agentAssistance;
        if (!assistance) return {status: 'none'};
        try {
            const {input, result} = assistance;
            window.InStockChainSupportContract.validate(result, input);
            if (input.theme !== record.target.theme || input.market !== record.target.market || input.asOf !== record.target.asOf
                || input.sourceNode.id !== record.target.source.id || input.targetNode.id !== record.target.target.id
                || input.claim !== record.target.relation || (input.claimAsOf || input.asOf) !== (record.claimDate || record.target.asOf)
                || input.evidence.sourceRef !== record.sourceRef.trim() || input.evidence.sourceDate !== record.sourceDate
                || input.evidence.locator !== record.locator.trim() || input.evidence.text !== record.quote.trim()) throw new Error('绑定输入与人工记录不同');
            return {status: record.decision === result.verdict ? 'same-decision' : 'human-overridden',
                suggestedDecision: result.verdict, manualResult: assistance.execution?.resultEntry === 'manual-json'};
        } catch (_) { return {status: 'unavailable', reason: '辅助记录不完整、未通过校验或与此人工意见不匹配，不能作为该意见的模型来源。'}; }
    }
    function appendAssistance(card, row) {
        const check = assistanceState(row);
        if (check.status === 'none') return;
        if (check.status === 'unavailable') { card.append(text('p', check.reason)); return; }
        const a = row.agentAssistance, details = document.createElement('details'); details.className = 'chain-review-assistance';
        details.append(text('summary', `人工：${decisions[row.decision]} / 辅助建议：${decisions[a.result.verdict]} · ${check.status === 'human-overridden' ? '人工已改判' : '判断一致，仍非事实认证'}`));
        details.append(text('p', check.manualResult ? '采用的辅助返回经人工导入或编辑，不等于模型原始回复。'
            : `采用的辅助返回来自${a.execution?.mode === 'newma' ? ' newma 宿主' : '本地 Agent'}任务，判断仍需人工核对。`),
            text('p', `主张对应日 ${a.input.claimAsOf || a.input.asOf} · 资料披露日 ${a.input.evidence.sourceDate}`),
            text('p', `执行来源 ${a.execution?.mode || '旧记录未提供'} · ${a.execution?.adapter || '宿主或旧记录未提供适配器'}${a.execution?.model ? ' · ' + a.execution.model : ''}`),
            text('p', `任务 ${a.execution?.taskId || '宿主或旧记录未提供任务号'} · 带入草稿 ${a.appliedAt || a.generatedAt || '旧记录未提供时间'}`),
            text('strong', '已采用辅助建议'), text('p', a.result.explanation));
        const dimensionNames = {subjects:'主体', direction:'关系方向', period:'时期', claimScope:'主张范围'};
        const values = {match:'匹配', mismatch:'不匹配', unclear:'未能确认'};
        details.append(text('p', Object.entries(dimensionNames).map(([key, label]) => `${label}：${values[a.result.checks[key]]}`).join(' · ')));
        a.result.citations.forEach(citation => { details.append(text('blockquote', citation.quote), text('p', citation.reason)); });
        if (a.result.gaps.length) details.append(text('p', '待补证据：' + a.result.gaps.join('；')));
        if (typeof a.originalResponse?.raw === 'string') {
            const original = document.createElement('details');
            original.append(text('summary', (a.originalResponse.origin === 'newma' ? '查看 newma 任务原始返回' : '查看本地任务原始返回') + (a.originalResponse.truncated ? '（已截断）' : '')),
                text('p', `收到返回 ${a.originalResponse.receivedAt || '未记录'}；保留原样，不保证格式或判断正确。`), text('pre', a.originalResponse.raw));
            details.append(original);
        } else details.append(text('p', '此记录未留存可对照的本地原始回复；宿主手动导入内容不能独立确认为模型原话。'));
        card.append(details);
    }
    window.InStockChainReviews = function ({bridge, onChange}) {
        const storage = window.InStockChainReviewStorage(bridge);
        const el = id => document.getElementById(`chain-review-${id}`);
        const root = el('panel'), select = el('relation'), status = el('status'), list = el('list'), confirm = el('confirm');
        const fields = ['decision', 'sourceRef', 'sourceDate', 'locator', 'quote', 'note', 'claimDate'];
        let data = null, targets = [], currentKey = '', drafts = new Map(), book = {schemaVersion: 1, entries: []};
        let revision = 0, state = 'idle', message = '请先读取复核记录；草稿不会自动保存。', sequence = 0;
        let archive, support;
        const scope = storage.scope;
        let currentScope = scope();
        function syncScope() {
            if (scope() === currentScope) return;
            currentScope = scope(); sequence += 1; revision = 0; state = 'idle'; book = {schemaVersion: 1, entries: []};
            drafts.clear(); currentKey = ''; data = null; targets = [];
            message = '存储范围或工作区身份变化，请重新读取研究与复核记录。';
        }
        function selected() { return targets[Number(select.value)] && select.value !== '' ? targets[Number(select.value)] : null; }
        function remember() {
            if (currentKey) drafts.set(currentKey, {...drafts.get(currentKey), ...Object.fromEntries(fields.map(field => [field, el(field).value]))});
        }
        function syncSupport() {
            support?.sync();
            const draft = drafts.get(currentKey);
            if (draft?.agentAssistance) {
                let matches = false;
                try {
                    const {requestId, ...bound} = draft.agentAssistance.input;
                    matches = JSON.stringify(bound) === JSON.stringify(getSupportInput());
                } catch (_) {}
                if (!matches) {
                    const previous = draft.agentAssistance.result;
                    if (draft.note.trim() === suggestionNote(previous).trim()) {
                        draft.note = ''; el('note').value = '';
                        if (draft.decision === previous.verdict) {
                            draft.decision = 'insufficient'; el('decision').value = 'insufficient';
                        }
                    }
                    delete draft.agentAssistance;
                }
            }
        }
        function edit() { remember(); confirm.checked = false; syncSupport(); onChange(); }
        function showDraft() {
            const target = selected(); currentKey = target ? key(target) : '';
            const draft = drafts.get(currentKey) || {decision: 'insufficient'};
            fields.forEach(field => { el(field).value = draft[field] || ''; }); confirm.checked = false;
            el('claimDate').value = draft.claimDate || target?.asOf || '';
            syncSupport();
        }
        function matches(record, target) {
            return matchesVersion(record, target, origin => archive?.isCurrent(origin));
        }
        function render() {
            const availability = storage.info(), available = availability.canRead;
            const busy = ['loading', 'saving', 'checking'].includes(state);
            el('load').disabled = !available || busy;
            el('save').disabled = !availability.canWrite || busy || state !== 'ready' || !selected();
            el('fields').disabled = busy || !selected(); select.disabled = busy || !targets.length;
            status.textContent = available ? message : availability.description;
            el('storage').textContent = availability.description + (available && !availability.canWrite ? '当前浏览器无安全写入锁，仅可读取与导出。' : '');
            const origin = drafts.get(currentKey)?.archiveSource;
            el('archive-status').textContent = origin ? `归档关联：${origin.security?.name || ''} · ${origin.periodEnd || ''} · PDF 第 ${origin.pdfPage} 页 · ${archive?.isCurrent(origin) ? '与本次读取版本一致，保存前再次核对' : '尚未核对、来源已更新或移除，不能沿用旧确认'}` : '';
            el('unlink').hidden = !origin; el('unlink').disabled = busy;
            document.getElementById('chain-archive-use').disabled = busy || !selected();
            document.querySelectorAll('.chain-relation-review').forEach(label => {
                const target = targets.find(item => item.source.id === label.dataset.source && item.target.id === label.dataset.target);
                const latest = target && state === 'ready' ? book.entries.filter(row => sameRelation(row.target, target)).at(-1) : null;
                const current = latest && matches(latest, target);
                label.textContent = state !== 'ready' ? '人工复核：尚未读取有效记录' : !latest ? '人工复核：尚无记录'
                    : current ? `人工复核：${decisions[latest.decision]} · 不改变系统评分` : '人工复核：旧记录与当前证据版本不同，待复核';
                label.classList.toggle('chain-review-contradicted', !!current && latest.decision === 'contradicted');
            });
            list.replaceChildren();
            const target = selected();
            const entries = (target ? book.entries.filter(row => sameRelation(row.target, target)) : book.entries).slice().reverse();
            if (state !== 'ready') { list.append(text('p', '尚未读取有效的已保存记录；草稿不代表保存成功。')); return; }
            if (!entries.length) list.append(text('p', target ? '此关系暂无已保存复核。' : '当前存储范围暂无已保存复核。'));
            entries.forEach((row, i) => {
                const card = document.createElement('article'); card.className = 'chain-review-record';
                card.append(text('strong', `${decisions[row.decision]} · ${row.target.source.name} → ${row.target.target.name}`),
                    text('p', `${row.target.theme} · 研究截至 ${row.target.asOf} · 复核 ${row.reviewedAt}`),
                    text('p', target && matches(row, target) ? (i === 0 ? '当前证据版本的最新人工意见' : '同版本较早意见，已被后续复核替代') : '历史参考：关系、日期或引用版本不同，需重新核对'),
                    text('p', row.target.relation));
                if (row.archiveSource) card.append(text('p', archive?.isCurrent(row.archiveSource) ? '归档原文与本次读取版本一致' : '归档原文尚未核对、已更新或已移除；此意见待复核'));
                if (row.sourceRef) {
                    let source = text('span', row.sourceRef);
                    try { const url = new URL(row.sourceRef); if (['http:', 'https:'].includes(url.protocol)) { source = text('a', row.sourceRef); source.href = url.href; source.target = '_blank'; source.rel = 'noopener noreferrer'; } } catch (_) { /* Document references remain text. */ }
                    card.append(source, text('p', `资料日期 ${row.sourceDate} · 定位 ${row.locator}`), text('pre', row.quote));
                }
                card.append(text('strong', '人工判断依据'), text('p', row.note));
                appendAssistance(card, row); list.append(card);
            });
        }
        async function perform(save) {
            syncScope();
            if (['loading', 'saving', 'checking'].includes(state) || (save && state !== 'ready')) return;
            const target = selected();
            if (!storage.info().canRead || (save && !storage.info().canWrite)) return;
            let next;
            if (save) {
                remember();
                syncSupport();
                const draft = drafts.get(currentKey);
                if (draft?.archiveSource) {
                    const checkingScope = scope(), checkingKey = currentKey, checkingSequence = ++sequence;
                    state = 'checking'; message = '正在重新核对归档原文版本…'; render();
                    const ok = await archive.refresh();
                    if (checkingSequence !== sequence || checkingScope !== scope()) return;
                    state = 'ready';
                    if (checkingKey !== currentKey || !ok || !archive.isCurrent(draft.archiveSource)) {
                        message = '归档原文已变化、移除或无法读取；草稿保留，请重新选择材料并核对。';
                        confirm.checked = false; render(); onChange(); return;
                    }
                }
                try {
                    if (!target || !draft || !confirm.checked) throw new Error('请确认已核对原文及当前关系后再保存。');
                    if (!draft.note.trim()) throw new Error('请填写判断依据或待补材料。');
                    if (draft.agentAssistance && draft.decision !== draft.agentAssistance.result.verdict
                        && draft.note.trim() === suggestionNote(draft.agentAssistance.result).trim())
                        throw new Error('你已改变辅助判断，请修改“判断依据”说明改判原因，不能仍原样保留模型理由。');
                    if (draft.archiveSource && (draft.sourceRef !== archiveRef(draft.archiveSource)
                        || draft.locator !== archiveLocator(draft.archiveSource)
                        || !draft.quote.trim() || !normalize(draft.archiveSource.text).includes(normalize(draft.quote))))
                        throw new Error('摘录、来源或页码与归档原文不符；请重新选取，或明确移除归档关联后填写其他证据。');
                    if (target.evidence.some(item => item.missing)) throw new Error('当前历史结果缺少引用目录，请重新导入完整研究包后复核。');
                    if (draft.decision !== 'insufficient' && (!draft.sourceRef.trim() || !draft.locator.trim() || !draft.quote.trim())) throw new Error('支持或反驳必须填写直接来源、原文定位及摘录。');
                    if ((draft.sourceRef || draft.sourceDate || draft.quote || draft.locator)
                        && (!day(draft.sourceDate) || draft.sourceDate > target.asOf || draft.sourceDate > new Date().toISOString().slice(0, 10))) throw new Error('请核对资料日期，不能晚于研究截止日；后续资料须在更新研究日期后复核。');
                    if (draft.archiveSource && day(draft.archiveSource.periodEnd) && draft.sourceDate < draft.archiveSource.periodEnd)
                        throw new Error('已披露财报原文的披露日期不能早于其报告期末，请核对原件。');
                    if (book.entries.length >= 200) throw new Error('已达到 200 条记录上限；请先导出留档，本轮不自动删除历史。');
                    const record = {...draft, id: crypto.randomUUID(), reviewedAt: new Date().toISOString(), reviewerUserId: storage.info().reviewerUserId,
                        snapshotId: data.snapshot.snapshot_id, target};
                    next = {schemaVersion: 1, entries: [...book.entries, record]};
                } catch (error) { message = error.message; render(); return; }
            }
            const operationScope = currentScope, operation = ++sequence;
            state = save ? 'saving' : 'loading'; message = save ? '正在追加复核记录…' : '正在读取复核记录…'; render(); onChange();
            try {
                const document = await (save ? storage.write(revision, next) : storage.read());
                const parsed = readBook(document.value);
                if (operation !== sequence || operationScope !== scope()) return;
                book = parsed; revision = document.revision; state = 'ready'; confirm.checked = false;
                message = save ? '已追加保存。人工意见不自动修改证据强度、研究评分或交易结论。' : `已读取 ${book.entries.length} 条复核。请核对当前版本；草稿保留。`;
            } catch (error) {
                if (operation !== sequence || operationScope !== scope()) return;
                state = 'failed'; message = error.message; confirm.checked = false;
            } finally { if (operation === sequence && operationScope === scope()) { render(); onChange(); } }
        }
        function setData(value) {
            syncScope(); remember(); data = value;
            archive?.clearSelection();
            targets = value ? (value.chain?.links || []).map(link => targetFor(value, link)) : [];
            const previous = currentKey;
            select.replaceChildren(new Option('请选择关系，不自动确认', ''), ...targets.map((target, index) => new Option(`${target.source.name} → ${target.target.name}`, String(index))));
            const match = targets.findIndex(target => key(target) === previous);
            select.value = match < 0 ? '' : String(match); showDraft(); render();
        }
        function context() {
            syncScope();
            const active = selected();
            const selectedReview = state === 'ready' && active ? book.entries.filter(row => sameRelation(row.target, active)).at(-1) || null : null;
            const comparison = selectedReview ? assistanceState(selectedReview) : null;
            const assistance = selectedReview?.agentAssistance;
            const contextualReview = selectedReview ? {...selectedReview, assistanceComparison: comparison,
                agentAssistance: !assistance ? undefined : comparison.status === 'unavailable' ? {status: 'unavailable'} : {...assistance,
                    originalResponse: assistance.originalResponse ? {available: true, truncated: assistance.originalResponse.truncated, receivedAt: assistance.originalResponse.receivedAt} : null}} : null;
            const relations = targets.map(target => {
                const latest = state === 'ready' ? book.entries.filter(row => sameRelation(row.target, target)).at(-1) : null;
                return {source: target.source.id, target: target.target.id,
                    label: `${target.source.name} → ${target.target.name}`, claim: target.relation,
                    review: latest ? {id: latest.id, decision: latest.decision, reviewedAt: latest.reviewedAt} : null,
                    applicability: state !== 'ready' ? 'unavailable' : !latest ? 'not-reviewed' : matches(latest, target) ? 'current-human-opinion' : 'needs-review'};
            });
            const candidateChecks = (data?.candidates || []).map(candidate => {
                const nodeId = (data.layers || []).find(layer => layer.id === candidate.layer_id)?.node_id;
                const related = nodeId ? relations.filter(row => row.source === nodeId || row.target === nodeId) : [];
                const checks = related.map(row => ({source: row.source, target: row.target,
                    label: row.label, claim: row.claim,
                    status: row.applicability === 'current-human-opinion' ? row.review.decision : row.applicability}));
                const status = !checks.length ? 'no-relations' : ['unavailable', 'contradicted', 'needs-review', 'insufficient', 'not-reviewed', 'supported'].find(value => checks.some(row => row.status === value));
                return {symbol: candidate.symbol, market: candidate.market, layerId: candidate.layer_id, nodeId,
                    status, relations: checks, supportedCount: checks.filter(row => row.status === 'supported').length,
                    relationCount: checks.length};
            });
            return {status: state, storage: storage.info(), revision, savedCount: state === 'ready' ? book.entries.length : null, archivedMaterials: archive?.context(), agentSuggestion: support?.context(),
                selectedRelation: active ? {source: active.source.id, target: active.target.id} : null,
                selectedReview: contextualReview,
                relations: state === 'ready' ? relations : [], candidateChecks,
                boundary: 'selectedReview/relations 为已保存人工意见；agentSuggestion 为待采纳辅助建议。candidateChecks 仅按候选所属节点的直接关联关系汇总，不证明公司受损或公司暴露成立，不做多跳传染、不改评分；不同证据版本需重新核对。'};
        }
        select.addEventListener('change', () => { remember(); showDraft(); render(); onChange(); });
        fields.forEach(field => el(field).addEventListener('input', edit));
        el('load').addEventListener('click', () => void perform(false));
        el('save').addEventListener('click', () => void perform(true));
        const normalize = value => value.replace(/\s+/g, ' ').trim();
        const archiveRef = origin => origin.sourceRef || `归档文件 ${origin.reportId} · 底稿 ${origin.workbookId} · 来源 ${origin.sourceId}`;
        const archiveLocator = origin => `PDF 物理第 ${origin.pdfPage} 页 · ${origin.sectionLabel}`;
        function getSupportInput() {
            const target = selected();
            if (!target || currentScope !== scope()) throw new Error('请先选择当前存储范围的复核关系。');
            const sourceRef = el('sourceRef').value.trim(), sourceDate = el('sourceDate').value;
            const locator = el('locator').value.trim(), quote = el('quote').value.trim();
            const claimAsOf = el('claimDate').value;
            if (!sourceRef || !locator || !quote || quote.length > 2000) throw new Error('请填写直接来源、原文定位和最多 2000 字的摘录。');
            if (!day(sourceDate) || sourceDate > target.asOf || sourceDate > new Date().toISOString().slice(0, 10)) throw new Error('请填写有效披露日期，不能晚于研究截止日或今天。');
            if (!day(claimAsOf) || claimAsOf > target.asOf) throw new Error('请核对主张对应日，不能晚于研究截止日。');
            const origin = drafts.get(currentKey)?.archiveSource;
            if (origin && (!archive?.isCurrent(origin) || sourceRef !== archiveRef(origin) || locator !== archiveLocator(origin)
                || !normalize(origin.text).includes(normalize(quote)) || (day(origin.periodEnd) && sourceDate < origin.periodEnd)))
                throw new Error('请先刷新归档并核对摘录、定位和披露日期。');
            return {theme: target.theme, market: target.market, asOf: target.asOf, claimAsOf, sourceNode: target.source, targetNode: target.target, claim: target.relation,
                evidence: {sourceRef, sourceDate, locator, text: quote, partial: true,
                    origin: origin ? {kind: 'archive-excerpt', workbookId: origin.workbookId, sourceId: origin.sourceId, reportId: origin.reportId, pdfPage: origin.pdfPage} : {kind: 'user-selected-excerpt'}}};
        }
        support = window.InStockChainSupport({bridge, getInput: getSupportInput, onChange, onApply(assistance) {
            if (['loading', 'saving', 'checking'].includes(state)) return;
            el('decision').value = assistance.result.verdict;
            el('note').value = suggestionNote(assistance.result);
            edit(); drafts.set(currentKey, {...drafts.get(currentKey), agentAssistance: assistance});
            message = '建议已带入草稿，尚未保存。请核对判断与引用，再明确勾选确认。'; render(); onChange();
        }});
        archive = window.InStockChainArchive({bridge, onChange: () => { support?.sync(); render(); onChange(); }, onUse({origin, quote}) {
            if (!selected() || ['loading', 'saving', 'checking'].includes(state)) return false;
            remember(); drafts.set(currentKey, {...drafts.get(currentKey), archiveSource: origin});
            el('sourceRef').value = archiveRef(origin); el('locator').value = archiveLocator(origin);
            el('quote').value = quote; el('sourceDate').value = ''; el('decision').value = 'insufficient';
            edit(); message = '归档摘录已带入当前关系草稿，未保存。请核对公司、期间、披露日期及关系支持度。'; render(); return true;
        }});
        el('unlink').addEventListener('click', () => {
            const draft = drafts.get(currentKey); if (!draft) return;
            delete draft.archiveSource;
            ['sourceRef', 'sourceDate', 'locator', 'quote'].forEach(field => {el(field).value = '';});
            el('decision').value = 'insufficient'; edit(); message = '已移除归档关联并清空摘录，未修改原件或已保存记录。'; render();
        });
        el('export').addEventListener('click', () => {
            syncScope(); if (state !== 'ready') { message = '先读取有效记录，再导出。'; render(); return; }
            const url = URL.createObjectURL(new Blob([JSON.stringify(book, null, 2)], {type: 'application/json'}));
            const link = document.createElement('a'); link.href = url; link.download = 'industry-chain-reviews.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        document.addEventListener('vibedesk:init', () => { const previous = currentScope; syncScope(); if (previous !== currentScope) setData(null); render(); onChange(); });
        render();
        return {setData, context, useQuote(value) {
            const index = targets.findIndex(target => target.source.id === value.source && target.target.id === value.target
                && target.evidence.some(item => item.id === value.evidenceId && item.sourceRef === value.sourceRef));
            if (index < 0) return;
            remember(); select.value = String(index); showDraft();
            const draft = drafts.get(currentKey); if (draft) delete draft.archiveSource;
            el('sourceRef').value = value.sourceRef; el('locator').value = value.locator; el('quote').value = value.quote;
            el('sourceDate').value = ''; el('decision').value = 'insufficient';
            edit(); message = '摘录已带入草稿，尚未保存。请核对披露日期及此原文是否支持关系；不会自动勾选确认。';
            render(); root.scrollIntoView({block: 'start'}); onChange();
        }, select(source, target) {
            remember(); const index = targets.findIndex(row => row.source.id === source && row.target.id === target);
            select.value = index < 0 ? '' : String(index); showDraft(); render(); root.scrollIntoView({block: 'start'}); onChange();
        }};
    };
})();
