(function () {
    'use strict';
    const contract = window.InStockChainReviewContract;
    const localKey = 'instock.chain-reviews.browser-local.v1';
    const empty = () => ({revision: 0, value: {schemaVersion: 1, entries: []}});
    const conflict = '记录已被其他页面更新。草稿保留，请重新读取、核对并确认后再保存。';
    function documentValue(result) {
        if (!Number.isSafeInteger(result?.revision) || result.revision < 0) throw new Error('复核记录版本格式异常，请重新读取。');
        return {revision: result.revision, value: contract.readBook(result.value)};
    }
    function readLocal() {
        let raw;
        try { raw = localStorage.getItem(localKey); }
        catch (_) { throw new Error('本机存储不可用，不能确认已保存；请保留草稿。'); }
        if (raw === null) return empty();
        let result;
        try { result = JSON.parse(raw); }
        catch (_) { throw new Error('复核记录格式异常；未视作空库，请先修复存储记录。'); }
        return documentValue(result);
    }
    window.InStockChainReviewStorage = function (bridge) {
        function info() {
            if (bridge?.embedded === false) return {
                mode: 'browser-local', label: '本浏览器复核', canRead: true, canWrite: !!navigator.locks?.request,
                reviewerUserId: 'standalone-browser-local',
                description: '仅当前浏览器、当前网址本机保存，不同步到 Desk；不是认证用户身份。更换端口、浏览器或清理站点数据后无法沿用，请导出留档。',
            };
            const config = bridge?.config;
            const available = !!(config?.session?.accessToken && config.user?.id && config.workspace?.id && config.instanceId && config.gateways?.storage);
            return {mode: 'desk', label: '工作区复核', canRead: available, canWrite: available,
                reviewerUserId: config?.user?.id,
                description: available ? '仅当前 Desk 工作区保存与读取，不使用独立页本机记录。' : 'Desk 会话或工作区存储未就绪；不回退到独立页本机记录。'};
        }
        const scope = () => JSON.stringify([bridge?.embedded === false ? 'browser-local' : 'desk',
            bridge?.config?.user?.id, bridge?.config?.workspace?.id, bridge?.config?.instanceId, bridge?.config?.gateways?.storage]);
        async function request(path, options = {}) {
            if (!info().canRead) throw new Error(info().description);
            const config = bridge.config;
            return fetch(path(config.gateways.storage), {...options, headers: {'Content-Type': 'application/json',
                Authorization: 'Bearer ' + config.session.accessToken, 'X-Newma-Desk-Instance-Id': config.instanceId}});
        }
        async function read() {
            if (info().mode === 'browser-local') return readLocal();
            const response = await request(url => url.replace(/\/$/, '') + '/relation-reviews/records');
            if (response.status === 404) return empty();
            if (!response.ok) throw new Error('工作区存储不可用，未确认保存；请重新读取核验。');
            return documentValue(await response.json());
        }
        async function write(expectedRevision, value) {
            const validated = contract.readBook(value);
            if (info().mode === 'browser-local') {
                if (!info().canWrite) throw new Error('当前浏览器不支持安全写入锁，不能保存复核；可读取与导出已有记录。');
                const originalScope = scope();
                return navigator.locks.request(localKey, () => {
                    if (scope() !== originalScope) throw new Error('存储范围已变化，请重新读取。');
                    const current = readLocal();
                    if (current.revision !== expectedRevision) throw new Error(conflict);
                    const result = {revision: current.revision + 1, value: validated};
                    try { localStorage.setItem(localKey, JSON.stringify(result)); }
                    catch (_) { throw new Error('本机保存失败，可能已禁用存储或空间不足；草稿保留，未确认保存。'); }
                    return result;
                });
            }
            const response = await request(url => url.replace(/\/$/, '') + '/relation-reviews/records',
                {method: 'PUT', body: JSON.stringify({expectedRevision, value: validated})});
            if (!response.ok) throw new Error(response.status === 409 ? conflict : '工作区存储不可用，未确认保存；请重新读取核验。');
            return documentValue(await response.json());
        }
        async function readRelations(input, {signal} = {}) {
            if (info().mode === 'browser-local') {
                const result = readLocal(), latest = new Map();
                for (const row of result.value.entries) {
                    if (row.target.theme !== input.theme || row.target.market !== input.market ||
                        !input.relations.some(relation => relation.source === row.target.source.id && relation.target === row.target.target.id)) continue;
                    // Match Desk's read-only projection; do not send full Agent transcripts to other pages.
                    const fields = ['id', 'decision', 'reviewedAt', 'snapshotId', 'target', 'sourceRef', 'sourceDate', 'locator', 'quote', 'note', 'reviewerUserId', 'claimDate', 'archiveSource'];
                    latest.set(JSON.stringify([row.target.source.id, row.target.target.id]),
                        Object.fromEntries(fields.filter(field => row[field] !== undefined).map(field => [field, row[field]])));
                }
                return {revision: result.revision, book: {schemaVersion: 1, entries: [...latest.values()]},
                    archive: {status: 'unavailable', revision: null, materials: []}};
            }
            const response = await request(url => url.replace(/\/storage\/?$/, '/sources/chain-reviews'),
                {method: 'POST', signal, body: JSON.stringify(input)});
            if (!response.ok) throw new Error('人工复核读取失败，请刷新模组或返回产业链核对；不能解释为没有风险。');
            const result = await response.json();
            documentValue({revision: result.revision, value: result.book});
            if (!['ready', 'unavailable'].includes(result.archive?.status) || !Array.isArray(result.archive.materials))
                throw new Error('归档版本信息不完整，请重新读取。');
            return result;
        }
        return {info, scope, read, write, readRelations};
    };
})();

