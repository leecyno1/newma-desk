(function () {
    'use strict';
    const decisions = {supported: '有直接支持', contradicted: '存在反证', insufficient: '证据不足'};
    const day = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
    function targetFor(data, link) {
        const nodes = data.chain.nodes;
        const node = id => { const item = nodes.find(row => row.id === id); return {id, name: item?.name || id, role: item?.role || ''}; };
        return {theme: data.theme, market: data.market, asOf: data.as_of, source: node(link.source), target: node(link.target),
            relation: link.relation, criticality: link.criticality,
            evidence: [...link.evidence_ids].sort().map(id => {
                const item = (data.evidence || []).find(row => row.id === id);
                return item ? {id, claim: item.claim, sourceRef: item.source_ref, observedAt: item.observed_at, strength: item.strength, sourceType: item.source_type} : {id, missing: true};
            })};
    }
    // Storage may reorder object fields; only values and array order are meaningful.
    const key = value => JSON.stringify(value, (_name, item) => item && typeof item === 'object' && !Array.isArray(item)
        ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
    const sameRelation = (a, b) => a.theme === b.theme && a.market === b.market && a.source.id === b.source.id && a.target.id === b.target.id;
    function readBook(value) {
        if (!value || value.schemaVersion !== 1 || !Array.isArray(value.entries) || value.entries.length > 200
            || !value.entries.every(row => row && typeof row.id === 'string' && row.id && Object.hasOwn(decisions, row.decision)
                && Number.isFinite(Date.parse(row.reviewedAt)) && typeof row.snapshotId === 'string'
                && row.target && typeof row.target.theme === 'string' && typeof row.target.market === 'string' && day(row.target.asOf)
                && typeof row.target.source?.id === 'string' && typeof row.target.target?.id === 'string'
                && typeof row.target.relation === 'string' && Array.isArray(row.target.evidence)
                && (!row.archiveSource || (typeof row.archiveSource.text === 'string' && typeof row.archiveSource.workbookId === 'string' && typeof row.archiveSource.sourceId === 'string' && Number.isInteger(row.archiveSource.pdfPage)))
                && ['sourceRef', 'sourceDate', 'locator', 'quote', 'note', 'reviewerUserId'].every(field => typeof row[field] === 'string')
                && row.note.trim() && (row.decision === 'insufficient' || (row.sourceRef.trim() && row.locator.trim() && row.quote.trim() && day(row.sourceDate) && row.sourceDate <= row.target.asOf)))
            || new Set(value.entries.map(row => row.id)).size !== value.entries.length) throw new Error('复核记录格式异常；未视作空库，请先修复存储记录。');
        return value;
    }
    const identity = value => key(['workbookId', 'workbookUpdatedAt', 'sourceId', 'section', 'reportId', 'pdfPage', 'pdfPageCount', 'periodEnd', 'basis', 'security', 'sourceRef', 'text', 'confirmedAt', 'truncated'].map(field => value[field]));
    window.InStockChainReviewContract = {decisions, day, targetFor, key, sameRelation, readBook, archiveIdentity: identity,
        matches(record, target, archiveCurrent) { return key(record.target) === key(target) && !target.evidence.some(item => item.missing) && (!record.archiveSource || archiveCurrent(record.archiveSource)); }};
})();
