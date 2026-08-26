(function () {
    'use strict';

    const pages = {
        'market-workbench': {title: '市场复盘', section: 'market'},
        'market-map': {title: '大盘云图', section: 'market'},
        rotation: {title: '行业与 ETF 轮动', section: 'market'},
        'event-flow': {title: '公司事件', section: 'stock'},
        'stock-candidates': {title: 'A/H 股候选', section: 'screen'},
        'technical-signals': {title: '选股中心', section: 'screen'},
        'stock-research': {title: '公司档案', section: 'stock'},
        czsc: {title: '缠论结构分析', section: 'stock'},
        'industry-chain': {title: '产业链研究', section: 'industry'},
        'strategy-validation': {title: '策略验证', section: 'review'},
        'research-book': {title: '研究组合', section: 'review'}
    };

    function currentPage() {
        const match = window.location.pathname.match(/\/mods\/([^/]+)/);
        return match && pages[match[1]] ? match[1] : 'market-workbench';
    }

    function setupNavigation() {
        const id = currentPage();
        const page = pages[id];
        document.title = page.title + ' · InStock 股票研究终端';
        const title = document.getElementById('stock-suite-current-title');
        if (title) title.textContent = page.title;
        document.querySelectorAll('[data-suite-page]').forEach(link => {
            link.classList.toggle('is-active', link.dataset.suitePage === id);
        });
        document.querySelectorAll('[data-suite-section]').forEach(section => {
            section.classList.toggle('is-active', section.dataset.suiteSection === page.section);
        });
    }

    function setupDirectory() {
        const button = document.getElementById('stock-suite-menu-button');
        const close = document.getElementById('stock-suite-directory-close');
        const directory = document.getElementById('stock-suite-directory');
        const backdrop = document.getElementById('stock-suite-backdrop');
        if (!button || !directory || !backdrop) return;
        function setOpen(open) {
            directory.classList.toggle('is-open', open);
            backdrop.hidden = !open;
            button.setAttribute('aria-expanded', String(open));
            document.body.style.overflow = open ? 'hidden' : '';
        }
        button.addEventListener('click', () => setOpen(!directory.classList.contains('is-open')));
        close && close.addEventListener('click', () => setOpen(false));
        backdrop.addEventListener('click', () => setOpen(false));
        document.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
        window.addEventListener('resize', () => { if (window.innerWidth > 900) setOpen(false); });
    }

    function setupHistory() {
        const moduleId = currentPage();
        const button = document.getElementById('stock-suite-history-button');
        const floatingButton = document.getElementById('stock-suite-history-fab');
        const buttons = [button, floatingButton].filter(Boolean);
        const close = document.getElementById('stock-suite-history-close');
        const drawer = document.getElementById('stock-suite-history');
        const list = document.getElementById('stock-suite-history-list');
        const counts = document.querySelectorAll('[data-stock-suite-history-count]');
        const banner = document.getElementById('stock-suite-history-banner');
        const latest = document.getElementById('stock-suite-history-latest');
        const moduleLabel = document.getElementById('stock-suite-history-module');
        if (!buttons.length || !drawer || !list) return;

        let selectedHistoryId = '';
        let selectedRecordType = 'analysis';
        let previousFocus = null;
        if (moduleLabel) moduleLabel.textContent = pages[moduleId].title;

        function setOpen(open) {
            drawer.classList.toggle('is-open', open);
            drawer.setAttribute('aria-hidden', String(!open));
            buttons.forEach(item => item.setAttribute('aria-expanded', String(open)));
            if (open) {
                previousFocus = document.activeElement;
                close && close.focus();
                loadList();
            } else if (previousFocus && previousFocus.focus) {
                previousFocus.focus();
            }
        }

        function errorMessage(body, fallback) {
            return body && body.error && typeof body.error === 'object'
                ? body.error.message || fallback
                : body && body.error || fallback;
        }

        function valueSummary(parameters) {
            const hidden = new Set(['refresh', 'filters', 'maxWorkers']);
            return Object.entries(parameters || {})
                .filter(([key, value]) => !hidden.has(key) && value !== null && value !== '' && value !== undefined)
                .slice(0, 3)
                .map(([key, value]) => `${key} ${Array.isArray(value) ? value.join('、') : value}`)
                .join(' · ');
        }

        function renderList(records) {
            list.replaceChildren();
            counts.forEach(count => {
                count.textContent = records.length;
                count.hidden = records.length === 0;
            });
            if (!records.length) {
                const empty = document.createElement('p');
                empty.textContent = '尚无历史记录。刷新或运行一次分析后会自动保留。';
                list.appendChild(empty);
                return;
            }
            records.forEach(record => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'stock-suite-history-item';
                item.classList.toggle('is-active', record.history_id === selectedHistoryId);
                const title = document.createElement('strong');
                title.textContent = record.title;
                const time = document.createElement('time');
                const generated = new Date(record.generated_at);
                time.textContent = Number.isNaN(generated.getTime())
                    ? record.generated_at
                    : generated.toLocaleString('zh-CN', {hour12: false});
                const detail = document.createElement('span');
                detail.textContent = [record.as_of ? `截止 ${record.as_of}` : '', valueSummary(record.parameters)].filter(Boolean).join(' · ') || '完整分析结果';
                item.append(title, time, detail);
                item.addEventListener('click', () => restore(record.history_id));
                list.appendChild(item);
            });
        }

        async function loadList() {
            try {
                const response = await fetch(`/api/v1/analysis-history?${new URLSearchParams({moduleId, limit: '50'})}`);
                const body = await response.json();
                if (!response.ok) throw new Error(errorMessage(body, '历史记录加载失败'));
                const records = body.data || [];
                renderList(records);
                return records;
            } catch (error) {
                list.replaceChildren();
                const message = document.createElement('p');
                message.textContent = error.message || String(error);
                list.appendChild(message);
                return [];
            }
        }

        async function restore(historyId, viewSource) {
            try {
                const response = await fetch(`/api/v1/analysis-history/${encodeURIComponent(historyId)}`);
                const body = await response.json();
                if (!response.ok) throw new Error(errorMessage(body, '历史记录读取失败'));
                const record = body.data;
                selectedHistoryId = record.history_id;
                selectedRecordType = record.record_type || 'analysis';
                const isHistory = viewSource !== 'latest';
                if (banner) banner.hidden = !isHistory;
                if (isHistory) document.documentElement.dataset.instockHistory = 'true';
                else delete document.documentElement.dataset.instockHistory;
                document.dispatchEvent(new CustomEvent('instock:history-selected', {
                    detail: {...record, view_source: isHistory ? 'history' : 'latest'},
                }));
                await loadList();
                setOpen(false);
            } catch (error) {
                window.alert(error.message || String(error));
            }
        }

        async function returnLatest() {
            selectedHistoryId = '';
            if (banner) banner.hidden = true;
            delete document.documentElement.dataset.instockHistory;
            const records = await loadList();
            const latestRecord = records.find(record => (record.record_type || 'analysis') === selectedRecordType);
            if (latestRecord) await restore(latestRecord.history_id, 'latest');
        }

        buttons.forEach(item => item.addEventListener('click', () => setOpen(!drawer.classList.contains('is-open'))));
        close && close.addEventListener('click', () => setOpen(false));
        latest && latest.addEventListener('click', returnLatest);
        document.addEventListener('keydown', event => { if (event.key === 'Escape' && drawer.classList.contains('is-open')) setOpen(false); });
        document.addEventListener('instock:analysis-rendered', event => {
            if (!event.detail || event.detail.moduleId !== moduleId || event.detail.source === 'history') return;
            selectedHistoryId = '';
            if (banner) banner.hidden = true;
            delete document.documentElement.dataset.instockHistory;
            loadList();
        });
        loadList();
    }

    function setupSearch() {
        const form = document.getElementById('stock-suite-search');
        const input = document.getElementById('stock-suite-symbol');
        if (!form || !input) return;
        const query = new URL(window.location.href).searchParams;
        input.value = query.get('symbol') || query.get('code') || '';
        form.addEventListener('submit', event => {
            event.preventDefault();
            const symbol = input.value.trim().toUpperCase();
            if (!/^[0-9]{6}(\.(SH|SZ|BJ))?$/.test(symbol)) {
                input.setCustomValidity('请输入 6 位 A 股代码');
                input.reportValidity();
                return;
            }
            input.setCustomValidity('');
            const url = new URL('/mods/stock-research', window.location.origin);
            url.searchParams.set('symbol', symbol);
            url.searchParams.set('period', 'daily');
            url.searchParams.set('bars', '240');
            window.location.assign(url.pathname + url.search);
        });
        input.addEventListener('input', () => input.setCustomValidity(''));
    }

    async function setupRuntime() {
        const root = document.querySelector('.stock-suite-runtime');
        const state = document.getElementById('stock-suite-runtime-state');
        if (!root || !state) return;
        try {
            const response = await fetch('/api/v1/health', {headers: {'Accept': 'application/json'}});
            const payload = await response.json();
            const health = payload && payload.ok === true ? payload.data : null;
            const analysisReady = response.ok && health && health.readiness && health.readiness.status === 'ready';
            const dataReady = analysisReady && health.readiness.market_data === true;
            root.classList.toggle('is-ready', dataReady);
            root.classList.toggle('is-degraded', analysisReady && !dataReady);
            root.classList.toggle('is-error', !analysisReady);
            state.textContent = dataReady ? '正常' : analysisReady ? '数据不可用' : '服务异常';
        } catch (error) {
            root.classList.add('is-error');
            state.textContent = '不可用';
        }
    }

    window.InStockAnalysisHistory = Object.freeze({
        moduleId: currentPage(),
        rendered(source) {
            document.dispatchEvent(new CustomEvent('instock:analysis-rendered', {
                detail: {moduleId: currentPage(), source: source || 'latest'},
            }));
        },
    });

    setupNavigation();
    setupDirectory();
    setupHistory();
    setupSearch();
    setupRuntime();
})();
