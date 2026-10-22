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

    function navigateWithinWorkspace(url) {
        const bridge = window.InStockNewmaDesk || window.InStockVibeDesk;
        if (!(bridge?.embedded ?? (window.parent !== window)) || url.origin !== window.location.origin) return false;
        const route = url.pathname.match(/^\/mods\/([^/]+)\/?$/)?.[1];
        if (!Object.hasOwn(pages, route || '')) return false;
        let notice = document.getElementById('stock-suite-navigation-error');
        if (bridge?.navigate?.('instock-' + route, url.search)) {
            if (notice) notice.remove();
        } else {
            if (!notice) {
                notice = document.createElement('div');
                notice.id = 'stock-suite-navigation-error';
                notice.className = 'alert alert-warning';
                notice.setAttribute('role', 'alert');
                document.body.prepend(notice);
            }
            notice.textContent = 'Desk 工作区导航尚未就绪，请刷新后重试；未切换到独立页面。';
        }
        return true;
    }

    function setupWorkspaceNavigation() {
        const follow = event => {
            if (event.defaultPrevented || (event.type === 'auxclick' && event.button !== 1)) return;
            const link = event.target.closest?.('a[href]');
            if (!link || link.hasAttribute('download')) return;
            const url = new URL(link.href, window.location.href);
            if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) return;
            if (navigateWithinWorkspace(url)) event.preventDefault();
        };
        document.addEventListener('click', follow);
        document.addEventListener('auxclick', follow);
    }

    function setupTheme() {
        const bridge = window.InStockNewmaDesk || window.InStockVibeDesk;
        const control = document.getElementById('stock-suite-theme-control');
        const select = document.getElementById('stock-suite-theme');
        if (!control || !select || !bridge) return;
        control.hidden = bridge.embedded;
        if (bridge.embedded) return;
        const sync = () => { select.value = bridge.themePreference; };
        sync();
        select.addEventListener('change', () => bridge.setStandaloneTheme(select.value));
        document.addEventListener('instock:themechange', sync);
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
        let scopeVersion = 0;
        let restoreVersion = 0;
        const bridge = window.InStockNewmaDesk || window.InStockVibeDesk;
        const request = (url) => bridge.fetchAnalysis(url);
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
                empty.textContent = '当前范围尚无历史记录。运行分析后会保留；旧版无工作区归属的记录仍在原库中，未自动认领或显示。';
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
            const version = scopeVersion;
            try {
                const response = await request(`/api/v1/analysis-history?${new URLSearchParams({moduleId, limit: '50'})}`);
                const body = await response.json();
                if (version !== scopeVersion) return [];
                if (!response.ok) throw new Error(errorMessage(body, '历史记录加载失败'));
                const records = body.data || [];
                renderList(records);
                return records;
            } catch (error) {
                if (version !== scopeVersion) return [];
                list.replaceChildren();
                const message = document.createElement('p');
                message.textContent = error.message || String(error);
                list.appendChild(message);
                return [];
            }
        }

        async function restore(historyId, viewSource) {
            const version = scopeVersion;
            const selection = ++restoreVersion;
            document.dispatchEvent(new CustomEvent('instock:history-loading', {detail: {moduleId}}));
            try {
                const response = await request(`/api/v1/analysis-history/${encodeURIComponent(historyId)}`);
                const body = await response.json();
                if (version !== scopeVersion || selection !== restoreVersion) return;
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
                if (version === scopeVersion && selection === restoreVersion) setOpen(false);
            } catch (error) {
                if (version !== scopeVersion || selection !== restoreVersion) return;
                document.dispatchEvent(new CustomEvent('instock:history-error', {detail: {moduleId}}));
                window.alert(error.message || String(error));
            }
        }

        async function returnLatest() {
            const selection = ++restoreVersion;
            const version = scopeVersion;
            selectedHistoryId = '';
            if (banner) banner.hidden = true;
            delete document.documentElement.dataset.instockHistory;
            const records = await loadList();
            if (version !== scopeVersion || selection !== restoreVersion) return;
            const latestRecord = records.find(record => (record.record_type || 'analysis') === selectedRecordType);
            if (latestRecord) await restore(latestRecord.history_id, 'latest');
        }

        buttons.forEach(item => item.addEventListener('click', () => setOpen(!drawer.classList.contains('is-open'))));
        document.addEventListener('vibedesk:init', () => {
            scopeVersion += 1;
            selectedHistoryId = '';
            if (banner) banner.hidden = true;
            delete document.documentElement.dataset.instockHistory;
            renderList([]);
            void loadList();
        });
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
        document.addEventListener('instock:analysis-invalidated', event => {
            if (event.detail?.moduleId !== moduleId) return;
            restoreVersion += 1;
            selectedHistoryId = '';
            if (banner) banner.hidden = true;
            delete document.documentElement.dataset.instockHistory;
            list.querySelectorAll('.is-active').forEach(item => item.classList.remove('is-active'));
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
            if (navigateWithinWorkspace(url)) return;
            window.location.assign(url.pathname + url.search);
        });
        input.addEventListener('input', () => input.setCustomValidity(''));
    }

    function setupRuntime() {
        const root = document.querySelector('.stock-suite-runtime');
        const state = document.getElementById('stock-suite-runtime-state');
        if (!root || !state) return;
        let pending = false;
        async function refresh() {
            if (pending) return;
            pending = true;
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
                root.classList.remove('is-ready', 'is-degraded');
                root.classList.add('is-error');
                state.textContent = '不可用';
            } finally {
                pending = false;
            }
        }
        document.addEventListener('instock:analysis-rendered', refresh);
        window.addEventListener('focus', refresh);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') refresh();
        });
        refresh();
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
    setupWorkspaceNavigation();
    setupTheme();
    setupDirectory();
    setupHistory();
    setupSearch();
    setupRuntime();
})();
