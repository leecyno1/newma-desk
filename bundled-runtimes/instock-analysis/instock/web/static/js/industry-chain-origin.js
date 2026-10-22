(function () {
    'use strict';
    const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
    window.InStockResearchOrigin = function ({bridge, root, mode, onChange, reference: suppliedReference}) {
        let record = null, handoff = null, value = null, message = '', busy = false, failed = false, sequence = 0, controller;
        const scope = () => JSON.stringify([bridge?.config?.user?.id, bridge?.config?.workspace?.id, bridge?.config?.instanceId]);
        let currentScope = scope();
        const query = new URLSearchParams(location.search);
        const reference = suppliedReference || (mode === 'read' && query.get('researchOriginId') ? {
            researchOriginId: query.get('researchOriginId'), originUserId: query.get('originUserId'), originWorkspaceId: query.get('originWorkspaceId')
        } : null);
        const available = () => !!(bridge?.config?.session?.accessToken && bridge.config.instanceId && bridge.config.gateways?.storage);
        function discard() {
            ++sequence; controller?.abort(); record = null; handoff = null; value = null; busy = false; failed = false; message = ''; currentScope = scope();
        }
        function render() {
            root.replaceChildren(); root.hidden = !record && !reference;
            if (root.hidden) return;
            root.append(text('h3', '研究起点 · 工作区私有记录'));
            const button = text('button', mode === 'save' ? handoff ? '研究起点已保存' : '保存本次研究起点' : '读取交接的图谱起点');
            button.type = 'button'; button.className = mode === 'save' ? 'chain-button chain-secondary' : 'dossier-review-load';
            button.disabled = busy || !record || !available() || (mode === 'save' && !!handoff);
            button.addEventListener('click', () => void execute()); root.append(button);
            const status = text('p', message || (!record ? '当前研究没有匹配的产业链结果，不能读取此交接。'
                : !available() ? '需在 Desk 当前工作区使用；独立页不猜身份。' : mode === 'save'
                    ? '保存后再进入公司档案，才会携带这次研究起点。只保存当次采集输入，不把当前图谱替换进历史结果。'
                    : '按指定记录读取历史研究起点，不自动认定企业关系。'));
            status.setAttribute('role', 'status'); root.append(status);
            if (!value) return;
            const input = value.record.input;
            root.append(text('strong', `${input.title} · 版本 ${input.versionNumber} · ${input.selectedNode.label}`),
                text('p', `研究截止 ${value.record.asOf} · 图谱保存 ${input.savedAt} · 起点归档 ${value.archivedAt}`), text('p', value.boundary));
            input.edges.forEach(edge => {
                const label = id => input.nodes.find(node => node.id === id)?.label || id;
                root.append(text('p', `${label(edge.source)} → ${label(edge.target)} · ${edge.label || '关系未说明'}`));
            });
            if (!input.evidence.length) root.append(text('p', '该研究起点没有保存逐条引用，不能据图谱箭头判断关系已核实。'));
            input.evidence.forEach(item => {
                const details = document.createElement('details'); details.className = 'dossier-review-record';
                details.append(text('summary', `${item.title} · ${{supports:'人工支持',refutes:'人工反证',unclear:'证据不足'}[item.judgment]}${item.reviewRequired ? ' · 待复核' : ''}`),
                    text('p', `资料日期 ${item.publishedAt || '未知'} · ${item.locator}`), text('blockquote', item.excerpt), text('p', item.note));
                if (item.reviewRequired) details.append(text('p', item.reviewRequired.reason));
                if (!item.publishedAt || item.publishedAt > value.record.asOf) details.append(text('p', !item.publishedAt
                    ? '资料日期未知，不能用于确认历史截止日事实。' : '资料晚于本次研究截止日，只能作后续线索。'));
                try { const url = new URL(item.url); if (['http:', 'https:'].includes(url.protocol) && !url.username && !url.password) {
                    const link = text('a', '打开原文'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; details.append(link);
                }} catch (_) {}
                root.append(details);
            });
        }
        async function execute() {
            if (!record || busy || !available()) return;
            const config = bridge.config, initialScope = scope(), operation = ++sequence;
            controller?.abort(); controller = new AbortController(); busy = true; failed = false; value = null; message = '处理中…'; render(); onChange();
            try {
                const headers = {Authorization: 'Bearer ' + config.session.accessToken, 'X-Newma-Desk-Instance-Id': config.instanceId};
                let url, options, id;
                if (mode === 'save') {
                    id = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
                    url = config.gateways.storage.replace(/\/$/, '') + '/research-origins/' + id;
                    options = {method:'PUT', headers:{...headers, 'Content-Type':'application/json'}, body:JSON.stringify({expectedRevision:0, value:record}), signal:controller.signal};
                } else {
                    url = new URL(config.gateways.storage.replace(/\/storage\/?$/, '/research-origins/') + encodeURIComponent(reference.researchOriginId), location.href);
                    url.search = new URLSearchParams({...record, sourceUserId:reference.originUserId || '', sourceWorkspaceId:reference.originWorkspaceId || ''});
                    options = {headers, signal:controller.signal};
                }
                const response = await fetch(url, options), result = await response.json();
                if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '研究起点保存或读取失败，请核对当前工作区。');
                if (operation !== sequence || initialScope !== scope()) return;
                if (mode === 'save') {
                    handoff = {researchOriginId:id, originUserId:config.user.id, originWorkspaceId:config.workspace.id};
                    message = '已保存本次研究起点。下方公司研究入口已携带记录标识；摘录未写入网址或共享快照。';
                } else {
                    value = result; message = '已读取历史研究起点；不是最新图谱，也不证明该公司与图谱环节直接关联。';
                }
            } catch (error) { if (operation === sequence) { failed = true; message = error.message; } }
            finally { if (operation === sequence) { busy = false; render(); onChange(); } }
        }
        function setData(data, input) {
            discard();
            if (mode === 'save' && data?.snapshot && input) record = JSON.parse(JSON.stringify({schemaVersion:'newma-desk.research-origin.v1',
                snapshotId:data.snapshot.snapshot_id, theme:data.theme, market:data.market, asOf:data.as_of, input}));
            if (mode === 'read' && reference && data?.exposure && data.research_context) {
                const context = data.research_context;
                record = {snapshotId:data.snapshot_id, theme:context.theme, market:context.market, asOf:context.as_of};
            }
            render();
        }
        function onInit() {
            if (currentScope !== scope()) { discard(); message = '工作区身份变化，请重新生成档案或恢复研究任务。'; render(); onChange(); }
        }
        document.addEventListener('vibedesk:init', onInit);
        function syncScope() { if (currentScope !== scope()) { discard(); render(); } }
        return {setData, dispose() { discard(); root.replaceChildren(); document.removeEventListener('vibedesk:init', onInit); },
            parameters() { syncScope(); return handoff || (value && record ? {...reference, researchOriginSnapshotId: record.snapshotId} : {}); }, context() {
            syncScope();
            return {status: busy ? 'loading' : failed ? 'failed' : value ? 'read' : handoff ? 'saved' : 'not-read-or-saved', message, reference: handoff || reference, value};
        }};
    };
})();
