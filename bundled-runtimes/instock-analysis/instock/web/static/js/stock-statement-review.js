(function () {
    'use strict';
    const fields = [['net_income', '合并净利润'], ['operating_cash_flow', '合并经营现金流净额'], ['assets', '合并总资产'], ['liabilities', '合并总负债']];
    const labels = {matched: '金额一致', different: '存在差异', incomparable: '期间或口径不一致', missing: '证据不足'};
    const boundary = '仅与当前档案金额对照，不是审计；不覆盖原指标、评分或历史版本。换证券、截止日或重新生成档案后需重新核对。';
    const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
    const amount = (value, unit) => Number.isFinite(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits: 2}) + ' ' + ({CNY: '元', USD: '美元', HKD: '港元'}[unit] || unit || '（单位未核实）') : '未提供';
    const period = (start, end) => end ? (start ? `${start} 至 ${end}` : `截至 ${end}`) : '期间未核实';
    function compare(data, report) {
        const symbol = String(data.identity?.symbol || '').split('.')[0];
        if (symbol !== report.symbol || report.contentOrigin !== 'pdf-text') throw new Error('原件证券或内容类型与当前档案不符');
        return fields.map(([id, label]) => {
            const raw = (data.fundamentals?.evidence || []).find(row => row.id === 'disclosure.cn_' + id);
            const facts = (report.facts || []).filter(row => row.id === id);
            const fact = facts.length === 1 ? facts[0] : null;
            let status = 'missing', difference = null;
            if (Number.isFinite(raw?.value) && Number.isFinite(fact?.value)) {
                const duration = ['net_income', 'operating_cash_flow'].includes(id);
                if (raw.asOf !== fact.asOf || raw.asOf !== report.periodEnd || raw.currency !== 'CNY' || raw.unit !== 'CNY'
                    || fact.currency !== 'CNY' || fact.unit !== 'CNY' || fact.scope !== 'consolidated'
                    || (duration && (!raw.periodStart || raw.periodStart !== fact.periodStart))) status = 'incomparable';
                else { difference = Math.round((raw.value - fact.value) * 100) / 100; status = difference === 0 ? 'matched' : 'different'; }
            }
            return {id, label, status, snapshotValue: raw?.value ?? null, snapshotPeriod: raw?.asOf || null,
                snapshotPeriodStart: raw?.periodStart || null, snapshotUnit: raw?.unit || null,
                snapshotCurrency: raw?.currency || null, snapshotSource: raw?.source || null, fact, difference};
        });
    }
    function create({root, bridge, onChange}) {
        let data = null, result = null, choices = null, sequence = 0, controller, pending = null, failure = null, lastOperation = null;
        const form = document.createElement('form'); form.className = 'dossier-statement-controls';
        const sourceLabel = text('label', '公告来源'); sourceLabel.htmlFor = 'statement-source';
        const source = document.createElement('select'); source.id = 'statement-source';
        for (const [value, title] of [['eastmoney', '东财公告'], ['cninfo', '巨潮官方公告']]) {
            const option = text('option', title); option.value = value; source.append(option);
        }
        const label = text('label', '公告链接或编号'); label.htmlFor = 'statement-announcement';
        const input = document.createElement('input'); input.id = 'statement-announcement'; input.placeholder = '粘贴东财公告链接或 AN 开头编号'; input.setAttribute('list', 'statement-announcement-options');
        const suggestions = document.createElement('datalist'); suggestions.id = 'statement-announcement-options';
        const button = text('button', '核对财报原件'); button.type = 'submit'; button.className = 'dossier-review-load';
        const find = text('button', '查找本公司巨潮财报'); find.type = 'button'; find.className = 'dossier-review-load';
        const status = text('p', '生成当前公司档案后可读取年度/半年度文字版财报。'); status.setAttribute('role', 'status');
        const output = document.createElement('div');
        form.append(sourceLabel, source, label, input, suggestions, button, find); root.append(form, status, output, text('p', boundary));
        root.append(link('在巨潮查询公告', 'https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search'));
        const scope = () => JSON.stringify([bridge?.config?.user?.id, bridge?.config?.workspace?.id, bridge?.config?.instanceId]);
        const available = () => data?.fundamentals?.mode === 'latest_snapshot';
        const authorized = action => !bridge?.embedded || Boolean(bridge.canInvokeAction?.(action));
        const canFind = () => available() && authorized('analysis.stock-statement-announcements');
        const canCompare = () => available() && authorized('analysis.stock-statement-evidence');
        function discard() { ++sequence; controller?.abort(); pending = null; failure = null; lastOperation = null; result = null; choices = null; output.replaceChildren(); button.disabled = !canCompare(); find.disabled = !canFind(); }
        function sourceHint() {
            input.placeholder = source.value === 'cninfo' ? '粘贴巨潮公告详情链接或数字公告编号' : '粘贴东财公告链接或 AN 开头编号';
            if (source.value === 'eastmoney') input.setAttribute('list', suggestions.id); else input.removeAttribute('list');
        }
        function selectedAnnouncement() {
            const raw = input.value.trim(), pattern = source.value === 'cninfo' ? /^\d{10,20}$/ : /^AN\d{10,30}$/;
            if (pattern.test(raw)) return raw;
            let url; try { url = new URL(raw); } catch (_) { return null; }
            if (!['http:', 'https:'].includes(url.protocol)) return null;
            const id = source.value === 'cninfo' && url.hostname === 'www.cninfo.com.cn' ? url.searchParams.get('announcementId')
                : source.value === 'eastmoney' && url.hostname === 'data.eastmoney.com' ? url.pathname.match(/\/(AN\d{10,30})\.html$/)?.[1] : null;
            return id && pattern.test(id) ? id : null;
        }
        function setData(value) {
            data = value; discard(); input.value = ''; suggestions.replaceChildren(); input.disabled = !available(); source.disabled = !available();
            status.textContent = !data ? '生成当前公司档案后可读取年度/半年度文字版财报。' : !available()
                ? '历史截止日模式不使用现在读取的原件补写过去判断。请清空截止日后核对当前档案。'
                : !canFind() || !canCompare() ? '当前 Desk 模组版本尚未授权完整财报核对功能，请更新公司档案模组后刷新；可先打开巨潮官网查看原件。'
                : '按需读取选定公告的合并三表，和本次档案金额逐项对照；不会自动采用。';
            for (const row of data?.disclosures?.announcements || []) {
                const id = String(row.url || '').match(/AN\d{10,30}/)?.[0];
                if (id && /年度报告/.test(row.title || '') && !/摘要/.test(row.title || '')) { const option = text('option', row.title); option.value = id; suggestions.append(option); }
            }
        }
        function link(label, url) {
            let parsed; try { parsed = new URL(url); } catch (_) { return text('span', label); }
            if (!['https:', 'http:'].includes(parsed.protocol)) return text('span', label);
            const node = text('a', label); node.href = parsed.href; node.target = '_blank'; node.rel = 'noopener noreferrer'; return node;
        }
        function render() {
            output.replaceChildren();
            const report = result.report;
            output.append(text('p', `${report.announcementSource === 'cninfo' ? '巨潮官方公告' : '东财公告'} · ${report.title} · 报告期 ${report.periodEnd} · 原件 ${report.pdfPageCount} 页 · 本次读取 ${report.readPages.length} 页`));
            output.append(link('打开完整财报原件', report.pdfUrl));
            if (report.reportPublishedAt || report.retrievedAt) output.append(text('p', `公告日期 ${report.reportPublishedAt || '未提供'} · 本次原件获取 ${report.retrievedAt || '未提供'}（不是历史版本日期）`));
            if (report.currencyEvidence) output.append(text('p', `币种依据（第 ${report.currencyEvidence.page} 页）：${report.currencyEvidence.excerpt}`));
            const wrap = document.createElement('div'); wrap.className = 'dossier-statement-table';
            const table = document.createElement('table'); table.setAttribute('aria-label', '原件金额对照');
            const head = document.createElement('tr'); ['科目', '当前档案', '原件金额', '对照结果', '定位与依据'].forEach(value => head.append(text('th', value)));
            const thead = document.createElement('thead'); thead.append(head); table.append(thead);
            const body = document.createElement('tbody');
            result.rows.forEach(row => {
                const tr = document.createElement('tr'); tr.dataset.status = row.status;
                const current = text('td', amount(row.snapshotValue, row.snapshotUnit));
                current.append(text('p', period(row.snapshotPeriodStart, row.snapshotPeriod)));
                if (row.snapshotCurrency && row.snapshotCurrency !== row.snapshotUnit) current.append(text('p', `币种声明 ${row.snapshotCurrency} · 与金额单位不一致，待核实`));
                const original = text('td', amount(row.fact?.value, row.fact?.unit));
                if (row.fact) original.append(text('p', period(row.fact.periodStart, row.fact.asOf)));
                tr.append(text('th', row.label), current, original,
                    text('td', labels[row.status] + (row.status === 'different' ? ` · 档案－原件 ${amount(row.difference, 'CNY')}` : '')));
                const source = document.createElement('td');
                if (row.fact) {
                    source.append(link(`金额第 ${row.fact.page} 页`, report.pdfUrl + '#page=' + row.fact.page), document.createTextNode(' · '), link(`表头第 ${row.fact.headerPage} 页`, report.pdfUrl + '#page=' + row.fact.headerPage));
                    const details = document.createElement('details'); details.append(text('summary', '表头与原文'), text('pre', row.fact.columnHeader + '\n' + row.fact.excerpt)); source.append(details);
                } else source.textContent = '未识别到可靠原始项目，不填零';
                tr.append(source); body.append(tr);
            });
            table.append(body); wrap.append(table); output.append(wrap);
            (report.warnings || []).forEach(warning => output.append(text('p', warning)));
        }
        source.addEventListener('change', () => { discard(); input.value = ''; sourceHint(); status.textContent = '公告来源已更改，请提供该来源的链接或编号；不会自动替换原件。'; onChange(); });
        input.addEventListener('input', () => {
            try {
                const url = new URL(input.value.trim());
                if (url.hostname === 'www.cninfo.com.cn') source.value = 'cninfo';
                if (url.hostname === 'data.eastmoney.com') source.value = 'eastmoney';
            } catch (_) { /* Plain announcement IDs use the explicitly selected source. */ }
            sourceHint(); discard(); status.textContent = '公告已更改，请重新核对；旧对照已撤下。'; onChange();
        });
        async function findReports() {
            if (!canFind()) throw new Error('当前档案状态或会话权限不支持查找财报');
            source.value = 'cninfo'; sourceHint(); input.value = ''; discard();
            pending = lastOperation = 'find';
            controller = new AbortController(); const operation = sequence, initialScope = scope();
            find.disabled = true; status.textContent = '正在查询本公司最近365日的巨潮财报…'; onChange();
            try {
                const symbol = String(data.identity.symbol).split('.')[0];
                const response = await bridge.fetchAnalysis('/api/v1/stock-research/statement-announcements?' + new URLSearchParams({symbol}), {signal: controller.signal});
                const body = await response.json(); if (!response.ok) throw new Error(body.error?.message || '财报列表读取失败');
                if (operation !== sequence || initialScope !== scope()) throw new Error('页面已变化，本次财报列表未采用');
                if (body.data.symbol !== symbol || body.data.source !== 'cninfo') throw new Error('返回列表不是当前公司巨潮公告');
                choices = body.data;
                output.append(text('p', `查询 ${choices.begin} 至 ${choices.end} · ${choices.boundary}`));
                if (choices.hasMore) output.append(text('p', '源结果超过一页，此处未显示全部结果；可用官方查询入口继续查找。'));
                const list = document.createElement('ul'); list.className = 'dossier-statement-candidates';
                for (const item of choices.items) {
                    const row = document.createElement('li'), choose = text('button', '选择'); choose.type = 'button';
                    choose.addEventListener('click', () => { source.value = 'cninfo'; sourceHint(); input.value = item.announcementId; discard(); status.textContent = `已选择 ${item.title}（公告 ${item.date}），请点击“核对财报原件”。`; onChange(); });
                    row.append(text('span', `${item.date} · ${item.title} · 报告期 ${item.periodEnd} `), choose, document.createTextNode(' · '), link('查看公告', item.url)); list.append(row);
                }
                output.append(list);
                status.textContent = choices.items.length ? `找到 ${choices.items.length} 份财报，请选择版本；尚未核对金额。` : '本次查询范围内未找到支持的年度/半年度报告，不代表公司没有披露。也可粘贴已知公告链接。';
                return choices;
            } catch (error) {
                if (operation === sequence && initialScope === scope()) { failure = error.message; status.textContent = `财报检索未完成：${failure}`; }
                throw error;
            } finally { if (operation === sequence && initialScope === scope()) { pending = null; find.disabled = !canFind(); onChange(); } }
        }
        async function verifySelected() {
            if (!canCompare()) throw new Error('当前档案状态或会话权限不支持原件核对');
            const id = selectedAnnouncement(), selectedSource = source.value;
            discard(); lastOperation = 'compare'; if (!id) { failure = '请提供与所选来源一致的公告详情链接或编号。'; status.textContent = failure; onChange(); throw new Error(failure); }
            pending = 'compare';
            const code = String(data.identity.symbol).split('.')[0];
            output.append(link('打开原公告核对', selectedSource === 'cninfo'
                ? `https://www.cninfo.com.cn/new/disclosure/detail?stockCode=${code}&announcementId=${id}`
                : `https://data.eastmoney.com/notices/detail/${code}/${id}.html`));
            controller = new AbortController(); const operation = sequence, initialScope = scope(), initialData = data;
            button.disabled = true; status.textContent = '正在读取原件并定位合并报表，尚未完成核对…'; onChange();
            try {
                const query = new URLSearchParams({symbol: data.identity.symbol, announcementId: id});
                if (selectedSource !== 'eastmoney') query.set('source', selectedSource);
                const response = await bridge.fetchAnalysis('/api/v1/stock-research/statement-evidence?' + query, {signal: controller.signal});
                const body = await response.json(); if (!response.ok) throw new Error(body.error?.message || '原件读取失败');
                if (operation !== sequence || initialScope !== scope()) throw new Error('页面已变化，本次原件核对未采用');
                const report = body.data;
                if (report.announcementId !== id || (report.announcementSource || 'eastmoney') !== selectedSource) throw new Error('返回原件与所选公告来源或编号不符，未用于核对');
                const rows = compare(initialData, report);
                result = {snapshotId: initialData.snapshot.snapshot_id, report, rows, boundary}; render();
                status.textContent = `金额一致 ${rows.filter(row => row.status === 'matched').length}/4 · 存在差异 ${rows.filter(row => row.status === 'different').length} 项 · 期间或口径不一致 ${rows.filter(row => row.status === 'incomparable').length} 项 · 证据不足 ${rows.filter(row => row.status === 'missing').length} 项；不是已审计。`;
                return result;
            } catch (error) {
                if (operation === sequence && initialScope === scope()) { failure = error.message; status.textContent = `未完成核对：${failure}`; }
                throw error;
            } finally { if (operation === sequence && initialScope === scope()) { pending = null; button.disabled = !canCompare(); onChange(); } }
        }
        find.addEventListener('click', () => findReports().catch(() => {}));
        form.addEventListener('submit', event => {
            event.preventDefault(); verifySelected().catch(() => {});
        });
        function actions() {
            const symbol = {type: 'string', description: '仅当前页面公司，不得切换证券'};
            return [
                {id: 'analysis.stock-statement-announcements', label: '查找当前公司财报', available: Boolean(canFind() && !pending),
                    inputSchema: {type: 'object', properties: {symbol}, additionalProperties: false}},
                {id: 'analysis.stock-statement-evidence', label: '核对选定财报原件', available: Boolean(canCompare() && !pending),
                    inputSchema: {type: 'object', properties: {symbol, announcementId: {type: 'string'}, source: {enum: ['eastmoney', 'cninfo']}}, additionalProperties: false}},
            ];
        }
        function runAction(id, values = {}) {
            const action = actions().find(item => item.id === id);
            if (!action) throw new Error('未知财报操作');
            if (pending) throw new Error('财报操作正在运行，请等待完成');
            if (!action.available) throw new Error('当前档案状态或会话权限不支持此财报操作');
            if (!values || typeof values !== 'object' || Array.isArray(values) || Object.keys(values).some(key => !(key in action.inputSchema.properties))) throw new Error('财报操作参数不受支持');
            if (values.symbol !== undefined && String(values.symbol).toUpperCase().split('.')[0] !== String(data.identity.symbol).toUpperCase().split('.')[0]) throw new Error('请求证券与当前公司档案不符');
            if (id === 'analysis.stock-statement-announcements') return findReports();
            const nextSource = values.source ?? source.value;
            if (!['eastmoney', 'cninfo'].includes(nextSource)) throw new Error('公告来源不受支持');
            if (values.announcementId !== undefined) {
                const pattern = nextSource === 'cninfo' ? /^\d{10,20}$/ : /^AN\d{10,30}$/;
                if (typeof values.announcementId !== 'string' || !pattern.test(values.announcementId)) throw new Error('公告编号与来源不一致');
                source.value = nextSource; sourceHint(); input.value = values.announcementId;
            } else if (nextSource !== source.value) throw new Error('更换来源须明确提供公告编号');
            return verifySelected();
        }
        setData(null);
        return {setData, actions, runAction, task: () => pending, context: () => result, choices: () => choices,
            feedback: () => ({state: pending ? 'running' : failure ? 'failed' : result || choices ? 'completed' : 'idle',
                operation: lastOperation, error: failure, message: status.textContent}),
            selection: () => ({source: source.value, announcementId: selectedAnnouncement()})};
    }
    window.InStockStatementReview = {create, compare};
})();
