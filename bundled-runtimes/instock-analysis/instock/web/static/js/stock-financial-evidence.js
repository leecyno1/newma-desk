/* Financial cards consume the dossier's filtered ledger, never the current clock. */
(function () {
    const fields = [
        ['pe', 'PE(TTM)', '倍', ['valuation.pe_ttm', 'valuation.pe']],
        ['pb', 'PB', '倍', ['valuation.pb']],
        ['valuationPercentile', '估值历史分位', '%', ['derived.valuation_percentile_midpoint']],
        ['revenueGrowthPct', '营收同比', '%', ['growth.revenue_yoy']],
        ['netProfitGrowthPct', '净利润同比', '%', ['growth.net_profit_yoy']],
        ['roePct', 'ROE', '%', ['profitability.roe']],
        ['grossMarginPct', '毛利率', '%', ['profitability.gross_margin']],
        ['netMarginPct', '净利率', '%', ['profitability.net_margin']],
        ['cashConversionPct', '盈利现金转化率', '%', ['derived.cash_conversion']],
        ['debtRatioPct', '资产负债率', '%', ['balance_sheet.debt_ratio', 'derived.debt_ratio']],
    ];
    window.InStockFinancialEvidence = function (root, fundamentals) {
        const ledger = fundamentals.evidence || [];
        const metrics = fundamentals.metrics || {};
        const rows = fields.map(([key, label, unit, ids]) => ({key, label, unit,
            value: metrics[key], evidence: ids.map(id => ledger.find(item => item.id === id)).find(Boolean)}));
        const proxy = ledger.find(item => item.id === 'derived.per_share_cash_earnings_proxy');
        if (proxy) rows.push({key: proxy.id, label: '每股现金流／EPS（参考）', unit: '倍', value: proxy.value, evidence: proxy});
        root.replaceChildren();
        rows.forEach(({key, label, unit, value, evidence}) => {
            const legacyCashEstimate = key === 'cashConversionPct' && (evidence?.dependsOn || []).includes('profitability.eps');
            const card = document.createElement('div');
            card.className = 'dossier-metric'; card.dataset.metric = key;
            const title = document.createElement('span'); title.textContent = legacyCashEstimate ? '历史每股口径估算（待复核）' : label;
            const amount = document.createElement('b');
            amount.textContent = typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}${unit}` : '--';
            const details = document.createElement('small');
            const date = evidence?.asOf;
            const period = date ? (evidence.periodStart ? `${evidence.periodStart}—${date}` : date) : '日期未提供';
            const quoteMetric = key === 'pe' || key === 'pb';
            const dateLabel = quoteMetric ? (evidence?.timeBasis === 'source_quote' ? '行情源时间' : evidence?.timeBasis === 'unknown' ? '行情源时间未核实' : '证据日期（旧快照，时间口径未核验）') : key === 'valuationPercentile' ? '历史样本截止日' : '报告期';
            details.textContent = `${dateLabel}：${period} · 来源：${evidence?.source || '未提供'}`;
            card.append(title, amount, details);
            if (evidence?.retrievedAt) {
                const fetched = document.createElement('small');
                fetched.textContent = `系统获取：${evidence.retrievedAt}（不代表实时行情）`;
                card.appendChild(fetched);
            }
            if (evidence?.publishedAt || evidence?.reportPublishedAt) {
                const publication = document.createElement('small');
                publication.textContent = evidence.publishedAt ? `该数值版本披露：${evidence.publishedAt}` : `报告披露：${evidence.reportPublishedAt}（当前数值版本未核验）`;
                card.appendChild(publication);
            }
            if (evidence?.sourceType === 'derived') {
                const source = document.createElement('details');
                const summary = document.createElement('summary'); summary.textContent = '计算与原始证据';
                const formula = document.createElement('small'); formula.textContent = `计算：${evidence.method || '方法未提供'}`;
                source.append(summary, formula);
                const dependencies = (evidence.dependsOn || []).map(id => ledger.find(item => item.id === id));
                dependencies.forEach(item => {
                    const fact = document.createElement('small');
                    if (!item) { fact.textContent = '依赖证据未提供'; source.appendChild(fact); return; }
                    const units = {CNY: '元', USD: '美元', 'CNY/share': '元/股', x: '倍'};
                    const number = typeof item.value === 'number' ? item.value.toLocaleString('zh-CN', {maximumFractionDigits: 4}) : '--';
                    fact.textContent = `${item.label || item.id}：${number}${units[item.unit] || item.unit || ''}；${item.periodStart ? item.periodStart + '—' : ''}${item.asOf || '报告期未知'}；${item.source || '来源未知'}；${item.publishedAt ? '版本披露 ' + item.publishedAt : item.reportPublishedAt ? '报告披露 ' + item.reportPublishedAt + '（当前版本未核验）' : '披露日期未知'}`;
                    source.appendChild(fact);
                    if (item.url && /^https?:\/\//i.test(item.url)) {
                        const link = document.createElement('a'); link.href = item.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = '查看该项来源'; source.appendChild(link);
                    }
                    if (item.note) { const note = document.createElement('small'); note.textContent = item.note; source.appendChild(note); }
                });
                card.appendChild(source);
            }
            if (legacyCashEstimate || evidence?.note || value == null) {
                const note = document.createElement('small');
                note.textContent = legacyCashEstimate ? '旧快照按每股口径估算，不能视为已核验的盈利现金转化率。原记录保留，请重新生成档案。' : evidence?.note || (key === 'cashConversionPct' ? '缺少同口径经营现金流与净利润；每股参考比值不替代本指标。' : '证据不足，未计为零。');
                card.appendChild(note);
            }
            root.appendChild(card);
        });
    };
})();
