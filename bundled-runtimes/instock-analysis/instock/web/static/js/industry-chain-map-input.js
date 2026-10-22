(function () {
    'use strict';
    window.InStockChainMapInput = function ({bridge, onChange}) {
        const el = id => document.getElementById('chain-graph-' + id);
        const panel = el('panel'), status = el('status'), preview = el('preview'), confirm = el('confirm');
        const query = new URLSearchParams(location.search);
        let handoff = query.get('sourceModule') === 'industry-map' ? query : null;
        let value = null, loading = false, busy = false, controller = null, generation = 0;
        const scope = () => JSON.stringify([bridge?.config?.user?.id, bridge?.config?.workspace?.id, bridge?.config?.instanceId]);
        let currentScope = scope();
        const text = (tag, content) => { const node = document.createElement(tag); node.textContent = content; return node; };
        function controls() { panel.querySelectorAll('button, input').forEach(node => { node.disabled = busy || loading; }); }
        function clear(message) {
            generation++; controller?.abort(); value = null; loading = false; confirm.checked = false;
            preview.replaceChildren(); status.textContent = message; controls(); onChange();
        }
        async function fetchInput(signal) {
            if (bridge?.whenReady) await bridge.whenReady();
            const config = bridge?.config;
            if (!config?.session?.accessToken || !config.instanceId || !config.gateways?.data) throw new Error('需从已授权的 Desk 工作区打开。');
            const url = new URL('/api/mods/instock-industry-chain/industry-map-inputs', config.gateways.data);
            for (const key of ['sector', 'node', 'version', 'revision', 'sourceUserId', 'sourceWorkspaceId']) url.searchParams.set(key, handoff.get(key) || '');
            const response = await fetch(url.href, {signal, headers: {Authorization: 'Bearer ' + config.session.accessToken, 'X-Newma-Desk-Instance-Id': config.instanceId}});
            const result = await response.json();
            if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '图谱交接读取失败，请回原模块核对。');
            if (result.schemaVersion !== 'newma-desk.industry-map-input.v1' || !Array.isArray(result.evidence)) throw new Error('图谱交接格式不受支持。');
            return result;
        }
        async function read() {
            if (!handoff || loading || busy) return;
            clear('正在读取指定工作区版本…'); loading = true; controls();
            const token = generation, initialScope = scope(); controller = new AbortController();
            try {
                const result = await fetchInput(controller.signal);
                if (token !== generation || initialScope !== scope()) return;
                value = result;
                preview.append(text('strong', `${result.title} · 版本 ${result.versionNumber} · ${result.selectedNode.label}`),
                    text('p', `仅 ${result.nodes.length} 个相关节点、${result.edges.length} 条直接关系、${result.evidence.length} 条记录；保存：${result.savedAt}`), text('p', result.boundary));
                result.edges.forEach(edge => {
                    const label = id => result.nodes.find(node => node.id === id)?.label || id;
                    preview.append(text('p', `${label(edge.source)} → ${label(edge.target)} · ${edge.label || '关系未说明'}`));
                });
                result.evidence.forEach(item => {
                    const details = document.createElement('details');
                    details.append(text('summary', `${item.title} · ${{supports:'人工支持',refutes:'人工反证',unclear:'证据不足'}[item.judgment]}${item.reviewRequired ? ' · 待复核' : ''}`),
                        text('p', `发布：${item.publishedAt || '未知'} · ${item.locator}`), text('blockquote', item.excerpt), text('p', item.note));
                    if (item.reviewRequired) details.append(text('p', `${item.reviewRequired.targetLabel}：${item.reviewRequired.reason}`));
                    try { const url = new URL(item.url); if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) { const link = text('a', '打开原文'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; details.append(link); } } catch (_) {}
                    preview.append(details);
                });
                status.textContent = '已读取原版本。确认后仅作为采集线索，保留反证、证据不足和待复核状态。';
            } catch (error) { if (token === generation) { value = null; status.textContent = error.message; } }
            finally { if (token === generation) { loading = false; controls(); onChange(); } }
        }
        async function material() {
            if (!handoff) return null;
            if (!value || !confirm.checked) throw new Error('请读取并确认图谱交接，或先移除此项交接；不会静默丢掉研究线索。');
            const token = generation, initialScope = scope();
            controller?.abort(); controller = new AbortController();
            try {
                const result = await fetchInput(controller.signal);
                if (token !== generation || initialScope !== scope()) throw new Error('交接条件已变化，请重新读取图谱。');
                return result;
            } catch (error) {
                if (token === generation) clear(error.message || '图谱输入复核失败，请重新读取。');
                throw error;
            }
        }
        function invalidateConfirmation() { confirm.checked = false; }
        el('load').addEventListener('click', () => void read());
        el('clear').addEventListener('click', () => { handoff = null; clear('已移除图谱交接，未修改原图谱。'); panel.hidden = true; });
        confirm.addEventListener('change', onChange);
        document.addEventListener('vibedesk:init', () => {
            const next = scope(); if (next !== currentScope) { currentScope = next; clear('工作区或页面身份变化，请重新读取图谱。'); }
        });
        panel.hidden = !handoff;
        status.textContent = '收到图谱版本与节点标识，请显式读取原记录；不会把网址当作证据。';
        return {material, invalidateConfirmation, context: () => handoff ? {status: loading ? 'loading' : value ? confirm.checked ? 'confirmed-as-research-input' : 'needs-confirmation' : 'not-loaded', input: value} : null,
            setBusy(next) { busy = next; controls(); }};
    };
})();
