(function initVibeDeskEmbed(window) {
    'use strict';

    const MODULE_IDS = Object.freeze([
        'dashboard',
        'ai-summary',
        'news-agg',
        'message-list',
        'email-messages',
        'minutes-agg',
        'folo-agg',
        'mp-agg',
        'send-management',
        'contact-management',
        'function-settings',
    ]);
    const DESK_MOD_IDS = Object.freeze({
        dashboard: 'deepsee-overview',
        'ai-summary': 'deepsee-ai-insights',
        'news-agg': 'deepsee-news',
        'message-list': 'deepsee-wechat',
        'email-messages': 'deepsee-email',
        'minutes-agg': 'deepsee-minutes',
        'folo-agg': 'deepsee-media',
        'mp-agg': 'deepsee-official-accounts',
        'send-management': 'deepsee-campaigns',
        'contact-management': 'deepsee-contacts',
        'function-settings': 'deepsee-settings',
    });

    function moduleFromPath(pathname) {
        const match = String(pathname || '').match(/^\/embed\/([a-z0-9-]+)\/?$/);
        return match && MODULE_IDS.includes(match[1]) ? match[1] : '';
    }

    const moduleId = moduleFromPath(window.location && window.location.pathname);
    if (!moduleId) return;
    const deskModId = DESK_MOD_IDS[moduleId];

    const state = {
        gatewayOrigin: '',
        moduleId: deskModId,
        userId: 'local-user',
        theme: '',
        appearance: null,
        parentOrigin: '',
        instanceId: '',
        grants: { permissions: [], actions: [] },
        connected: false,
    };
    const appliedAppearanceVariables = new Set();
    const configListeners = new Set();
    const pendingActions = new Map();
    const activeTasks = new Map();

    document.documentElement.classList.add('vibedesk-embed');
    document.documentElement.dataset.vibedeskModule = moduleId;
    // Embedded pages are display clients. Deepsee's backend owns scheduled sync.
    window.__autoModuleRefreshBound = true;

    function exactHttpOrigin(value) {
        try {
            const parsed = new URL(String(value || ''));
            if (!['http:', 'https:'].includes(parsed.protocol)) return '';
            if (parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) return '';
            return parsed.origin;
        } catch (_) {
            return '';
        }
    }

    function selectEmbeddedModule() {
        document.querySelectorAll('.module-tabs .tab[data-module]').forEach((tab) => {
            tab.classList.toggle('active', tab.dataset.module === moduleId);
        });
        document.querySelectorAll('.module-panel[id]').forEach((panel) => {
            panel.classList.toggle('active', panel.id === moduleId);
        });
    }

    function buildSettingsSecondaryNavigationFallback() {
        const panel = document.getElementById('function-settings');
        const container = panel && panel.querySelector('.settings-container');
        if (!panel || !container) return false;

        let layout = panel.querySelector('.settings-layout');
        let sidebar = panel.querySelector('.settings-sidebar');
        let content = panel.querySelector('.settings-content');
        if (!layout) {
            layout = document.createElement('div');
            layout.className = 'settings-layout';
            panel.insertBefore(layout, container);
        }
        if (!sidebar) {
            sidebar = document.createElement('div');
            sidebar.className = 'settings-sidebar';
            layout.insertBefore(sidebar, layout.firstChild || null);
        }
        if (!content) {
            content = document.createElement('div');
            content.className = 'settings-content';
            layout.appendChild(content);
        }
        if (container.parentElement !== content) content.appendChild(container);

        const sections = Array.from(container.querySelectorAll('.settings-section')).filter((section) => {
            return section.dataset.navHidden !== '1' && !section.closest('.modal');
        });
        if (!sections.length) return false;

        const showSection = (targetId) => {
            const nextId = sections.some((section) => section.id === targetId)
                ? targetId
                : sections[0].id;
            sections.forEach((section) => {
                const active = section.id === nextId;
                section.classList.toggle('hidden', !active);
                section.classList.toggle('active-settings-section', active);
                section.style.display = active ? 'block' : 'none';
            });
            sidebar.querySelectorAll('.settings-nav-item').forEach((item) => {
                item.classList.toggle('active', item.dataset.target === nextId);
            });
            try { content.scrollTo({ top: 0, behavior: 'auto' }); } catch (_) {}
        };

        sidebar.replaceChildren();
        sections.forEach((section, index) => {
            if (!section.id) section.id = `settings-sec-${index}`;
            const title = String(
                section.dataset.navTitle
                || section.querySelector('h3')?.textContent
                || `设置 ${index + 1}`
            ).trim();
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'settings-nav-item';
            item.dataset.target = section.id;
            item.textContent = title;
            item.addEventListener('click', () => showSection(section.id));
            sidebar.appendChild(item);
        });

        const defaultId = sections.some((section) => section.id === 'settings-home')
            ? 'settings-home'
            : sections[0].id;
        showSection(defaultId);
        panel._layout = true;
        return sidebar.querySelectorAll('.settings-nav-item').length > 0;
    }

    function ensureSettingsSecondaryNavigation(allowFallback = false) {
        if (moduleId !== 'function-settings') return true;
        const panel = document.getElementById('function-settings');
        if (!panel) return false;
        if (panel.querySelector('.settings-sidebar .settings-nav-item')) return true;

        try {
            if (typeof window.initSettingsLayout === 'function') window.initSettingsLayout();
        } catch (_) {}
        if (panel.querySelector('.settings-sidebar .settings-nav-item')) return true;
        return allowFallback ? buildSettingsSecondaryNavigationFallback() : false;
    }

    function activateEmbeddedModule() {
        selectEmbeddedModule();
        let attempts = 0;
        let nativeActivated = false;
        const maxAttempts = 60;

        const activate = () => {
            attempts += 1;
            const tab = document.querySelector(`.module-tabs .tab[data-module="${moduleId}"]`);
            if (!nativeActivated && tab && window.__BOOTSTRAPPED__) {
                nativeActivated = true;
                try { tab.click(); } catch (_) {}
            }

            if (nativeActivated && ensureSettingsSecondaryNavigation(false)) return;
            if (attempts < maxAttempts) {
                window.requestAnimationFrame(activate);
                return;
            }

            // Keep the requested panel usable even if Deepsee's main bootstrap changes upstream.
            selectEmbeddedModule();
            ensureSettingsSecondaryNavigation(true);
        };

        window.requestAnimationFrame(activate);
    }

    function applyAppearance(appearance) {
        const cssVars = appearance && typeof appearance === 'object' && appearance.cssVars
            && typeof appearance.cssVars === 'object'
            ? appearance.cssVars
            : {};
        const nextVariables = new Set();
        Object.entries(cssVars).forEach(([name, value]) => {
            if (!/^--[a-z0-9-]{2,80}$/.test(name) || typeof value !== 'string' || value.length > 200) return;
            document.documentElement.style.setProperty(name, value);
            nextVariables.add(name);
        });
        appliedAppearanceVariables.forEach((name) => {
            if (!nextVariables.has(name)) document.documentElement.style.removeProperty(name);
        });
        appliedAppearanceVariables.clear();
        nextVariables.forEach((name) => appliedAppearanceVariables.add(name));
    }

    function applyTheme(theme, appearance = null) {
        const normalized = theme === 'dark' ? 'dark' : 'light';
        const compatibleAppearance = appearance && appearance.mode === normalized
            ? appearance
            : null;
        state.theme = normalized;
        state.appearance = compatibleAppearance;
        applyAppearance(state.appearance);
        document.documentElement.dataset.theme = normalized;
        document.documentElement.dataset.vibedeskTheme = normalized;
        document.documentElement.classList.toggle('light', normalized === 'light');
        document.documentElement.classList.toggle('dark', normalized === 'dark');
        document.documentElement.style.colorScheme = normalized;
        if (!document.body) return;
        document.body.classList.toggle('theme-hacker', normalized === 'dark');
        const button = document.getElementById('themeToggle');
        if (typeof window.applyThemeToggleMarkup === 'function') {
            window.applyThemeToggleMarkup(button, normalized === 'dark');
        }
        try {
            if (typeof window.renderDashboard === 'function' && moduleId === 'dashboard') {
                window.renderDashboard();
            }
        } catch (_) {}
        try {
            window.dispatchEvent(new CustomEvent('newma:themechange', {
                detail: { mode: normalized, appearance: state.appearance },
            }));
        } catch (_) {}
    }

    function notifyConfig() {
        const snapshot = Object.freeze({ ...state, embedModule: moduleId });
        configListeners.forEach((listener) => {
            try { listener(snapshot); } catch (_) {}
        });
        try {
            window.dispatchEvent(new CustomEvent('vibedesk:config', { detail: snapshot }));
        } catch (_) {}
    }

    function sendReady() {
        if (window.parent === window) return;
        window.parent.postMessage({ type: 'vibedesk:ready' }, '*');
    }

    function sendHello() {
        if (window.parent === window) return;
        window.parent.postMessage({
            type: 'vibedesk:hello',
            modId: deskModId,
            protocolVersions: ['1.0'],
            capabilities: ['actions', 'agent', 'context', 'theme'],
        }, '*');
    }

    function nextRequestId() {
        return window.crypto?.randomUUID?.()
            || `deepsee-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    function textAt(id) {
        return String(document.getElementById(id)?.textContent || '').trim();
    }

    function pageContext() {
        const panel = document.getElementById(moduleId);
        const heading = String(
            panel?.dataset.panelTitle
            || panel?.querySelector('h1,h2,.news-title,.analysis-title-main')?.textContent
            || deskModId
        ).trim().slice(0, 160);
        const visibleBlocks = Array.from(
            panel?.querySelectorAll('h2,h3,.news-card-title,.summary-section') || []
        ).slice(0, 40).map((element, index) => ({
            id: String(element.id || `block-${index + 1}`).slice(0, 128),
            type: element.classList.contains('summary-section') ? 'analysis' : 'section',
            title: String(
                element.querySelector?.('h2,h3,.news-card-title')?.textContent
                || element.textContent
                || ''
            ).trim().replace(/\s+/g, ' ').slice(0, 160),
        })).filter((block) => block.title);
        const filters = moduleId === 'ai-summary'
            ? {
                period: String(document.querySelector('.time-tab.active')?.dataset.period || '1day'),
                modules: Array.from(document.querySelectorAll('.module-toggle:checked'))
                    .map((item) => item.dataset.module)
                    .filter(Boolean),
            }
            : moduleId === 'news-agg'
                ? {
                    keyword: String(document.getElementById('newsSearchInput')?.value || '').trim(),
                    source: String(document.getElementById('newsSourceSelect')?.value || '').trim(),
                }
                : {};
        const summary = moduleId === 'ai-summary'
            ? { status: textAt('analysisStatus') || '准备就绪' }
            : moduleId === 'news-agg'
                ? {
                    status: textAt('newsEngineStatus'),
                    total: textAt('newsMetricTotal'),
                    sentiment: textAt('newsMetricSentiment'),
                    velocity: textAt('newsMetricVelocity'),
                    risks: textAt('newsMetricRisks'),
                }
                : {};
        return {
            view: { id: deskModId, title: heading || deskModId },
            visibleBlocks,
            selection: {},
            filters,
            data: { freshness: 'unknown', summary },
            actions: state.grants.actions.map((id) => ({ id, available: true })),
            tasks: Array.from(activeTasks.values()).slice(-20).map((task) => ({
                id: task.id,
                status: task.status,
                ...(task.actionId ? { actionId: task.actionId } : {}),
            })),
        };
    }

    function publishContext(requestId = nextRequestId()) {
        if (!state.connected || !state.parentOrigin || !state.instanceId) return;
        window.parent.postMessage({
            type: 'vibedesk:context',
            requestId,
            instanceId: state.instanceId,
            modId: state.moduleId,
            context: pageContext(),
        }, state.parentOrigin);
    }

    async function gatewayRequest(path, payload, options = {}) {
        if (!state.gatewayOrigin) throw new Error('VibeDesk Gateway is not configured');
        const method = options.method || 'POST';
        const hasBody = method !== 'GET' && method !== 'HEAD';
        const response = await fetch(`${state.gatewayOrigin}${path}`, {
            method,
            credentials: 'omit',
            redirect: 'error',
            headers: {
                Accept: 'application/json',
                ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
                ...(options.userScoped ? { 'X-User-Id': state.userId } : {}),
            },
            ...(hasBody ? { body: JSON.stringify(payload || {}) } : {}),
        });
        let body;
        try { body = await response.json(); } catch (_) { body = undefined; }
        if (!response.ok) {
            const detail = body && typeof body.detail === 'string'
                ? body.detail
                : `VibeDesk Gateway returned HTTP ${response.status}`;
            throw new Error(detail);
        }
        return body;
    }

    function agentDisplayName(id) {
        return ({
            'codex-cli': 'Codex CLI',
            'claude-cli': 'Claude Code',
            'gemini-cli': 'Gemini CLI',
            'qoder-cli': 'Qoder CLI',
            'minimax-cli': 'MiniMax CLI',
            'hermes-webui': 'Hermes WebUI',
            'openai-compatible': '模型通道',
            'anthropic': 'Anthropic 模型通道',
        })[id] || id || '未配置';
    }

    function renderAgentSettings(preferences, capabilityPayload, deepseeConfig) {
        const grid = document.getElementById('deskAgentProfileGrid');
        const status = document.getElementById('deskAgentStatus');
        if (!grid || !status) return;
        const settingsLink = document.getElementById('deskAgentSettingsLink');
        if (settingsLink) {
            let deskOrigin = state.parentOrigin;
            if (!deskOrigin) {
                try { deskOrigin = new URL(document.referrer).origin; } catch (_) { deskOrigin = ''; }
            }
            settingsLink.href = `${deskOrigin || 'http://127.0.0.1:5888'}/?view=agent-settings`;
            settingsLink.target = '_top';
        }
        const profiles = [
            ['deep', '深度研究'],
            ['batch', '批量处理'],
            ['edit', '编码修改'],
            ['quick', '快速问答'],
        ];
        const targets = preferences?.profileTargets || {};
        const adapters = Array.isArray(capabilityPayload?.adapters)
            ? capabilityPayload.adapters
            : [];
        const agent = deepseeConfig?.desk_agent || {};
        const adapterSelect = document.getElementById('deskAgentAdapter');
        const modelOptions = document.getElementById('deskAgentModelOptions');
        const updateModelOptions = () => {
            if (!modelOptions) return;
            modelOptions.replaceChildren();
            const selectedAdapter = adapters.find((item) => item && item.id === adapterSelect?.value);
            (selectedAdapter?.models || []).forEach((model) => {
                const option = document.createElement('option');
                option.value = String(model);
                modelOptions.appendChild(option);
            });
        };
        if (adapterSelect) {
            adapterSelect.replaceChildren();
            const inherited = document.createElement('option');
            inherited.value = '';
            inherited.textContent = '沿用 Desk 全局 batch 路由';
            adapterSelect.appendChild(inherited);
            adapters.filter((item) => item && item.kind === 'local-cli').forEach((item) => {
                const option = document.createElement('option');
                option.value = String(item.id || '');
                option.textContent = `${agentDisplayName(item.id)}${item.available === false ? '（未安装）' : ''}`;
                option.disabled = item.available === false;
                adapterSelect.appendChild(option);
            });
            adapterSelect.value = String(agent.adapter || '');
            adapterSelect.onchange = updateModelOptions;
        }
        const modelInput = document.getElementById('deskAgentModel');
        if (modelInput) modelInput.value = String(agent.model || '');
        updateModelOptions();
        const profileSelect = document.getElementById('deskAgentCommandProfile');
        if (profileSelect) profileSelect.value = String(agent.commandProfile || agent.command_profile || 'batch');
        grid.replaceChildren();
        profiles.forEach(([id, label]) => {
            const card = document.createElement('div');
            card.className = 'settings-runtime-card';
            const target = String(targets[id] || (id === 'quick' ? 'openai-compatible' : preferences?.defaultAdapter || ''));
            const adapter = adapters.find((item) => item && item.id === target);
            const availability = adapter && adapter.available === false ? '不可用' : '已配置';
            card.innerHTML = `<div class="settings-runtime-name"></div><div class="settings-runtime-meta"></div>`;
            card.querySelector('.settings-runtime-name').textContent = label;
            card.querySelector('.settings-runtime-meta').textContent = `${agentDisplayName(target)} · ${availability}`;
            grid.appendChild(card);
        });
        const count = adapters.filter((item) => item && item.available !== false).length;
        status.textContent = `已连接 · ${count} 个入口可用`;
    }

    async function refreshAgentSettings() {
        if (moduleId !== 'function-settings') return;
        const status = document.getElementById('deskAgentStatus');
        if (status) status.textContent = '读取中…';
        try {
            const [preferences, capabilities, deepseeConfig] = await Promise.all([
                gatewayRequest('/api/agent/preferences', null, { method: 'GET', userScoped: true }),
                gatewayRequest('/api/capabilities', null, { method: 'GET' }),
                fetch('/api/ai/config', { headers: { Accept: 'application/json' } }).then((response) => response.ok ? response.json() : ({})),
            ]);
            renderAgentSettings(preferences, capabilities, deepseeConfig);
        } catch (error) {
            if (status) status.textContent = `连接失败：${String(error?.message || error).slice(0, 60)}`;
        }
    }

    window.__vibedeskRefreshAgentSettings = refreshAgentSettings;

    function invokeAction(actionId, input = {}) {
        if (!state.connected || !state.instanceId || !state.parentOrigin) {
            return Promise.reject(new Error('Newma-Desk Action bridge is not ready'));
        }
        if (!state.grants.actions.includes(actionId)) {
            return Promise.reject(new Error(`Action is not granted: ${actionId}`));
        }
        const requestId = nextRequestId();
        return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
                pendingActions.delete(requestId);
                reject(new Error('Newma-Desk Action timed out'));
            }, 300000);
            pendingActions.set(requestId, { actionId, resolve, reject, timer });
            window.parent.postMessage({
                type: 'vibedesk:action-request',
                requestId,
                instanceId: state.instanceId,
                modId: state.moduleId,
                actionId,
                input,
            }, state.parentOrigin);
        });
    }

    async function waitForTask(task, options = {}) {
        const taskId = typeof task === 'string' ? task : task?.id;
        if (!taskId) throw new Error('Agent task id is missing');
        const actionId = options.actionId || '';
        const timeoutMs = Math.max(1000, Math.min(300000, Number(options.timeoutMs || 300000)));
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            const current = await gatewayRequest(
                `/api/agent/tasks/${encodeURIComponent(taskId)}`,
                null,
                { method: 'GET', userScoped: true }
            );
            activeTasks.set(taskId, { id: taskId, status: current.status || 'unknown', actionId });
            if (['completed', 'failed', 'cancelled'].includes(current.status)) {
                publishContext();
                if (current.status !== 'completed') {
                    throw new Error(current.error || `Agent task ${current.status}`);
                }
                return current;
            }
            await new Promise((resolve) => window.setTimeout(resolve, 500));
        }
        throw new Error('Agent task timed out');
    }

    const bridge = Object.freeze({
        isEmbedded: window.parent !== window,
        embedModule: moduleId,
        getConfig() {
            return Object.freeze({ ...state, embedModule: moduleId });
        },
        onConfig(listener) {
            if (typeof listener !== 'function') throw new TypeError('listener must be a function');
            configListeners.add(listener);
            if (state.gatewayOrigin) listener(this.getConfig());
            return () => configListeners.delete(listener);
        },
        createAgentTask(input = {}) {
            return gatewayRequest('/api/agent/tasks', {
                ...input,
                moduleId: state.moduleId || input.moduleId || moduleId,
            }, { userScoped: true });
        },
        createModelResponse(input = {}) {
            return gatewayRequest('/api/model/responses', {
                ...input,
                moduleId: state.moduleId || input.moduleId || moduleId,
            });
        },
        canInvokeAction(actionId) {
            return state.connected && state.grants.actions.includes(actionId);
        },
        invokeAction,
        waitForTask,
        publishContext,
    });
    window.VibeDeskBridge = bridge;

    window.addEventListener('message', (event) => {
        if (event.source !== window.parent) return;
        const data = event.data;
        if (!data || typeof data !== 'object') return;

        if (data.type === 'vibedesk:init') {
            if (
                data.protocolVersion !== '1.0'
                || data.modId !== deskModId
                || !data.instanceId
                || !data.gateways?.actions
            ) return;
            let gatewayOrigin = '';
            try { gatewayOrigin = new URL(data.gateways.actions).origin; } catch (_) { return; }
            if (gatewayOrigin !== event.origin) return;
            state.gatewayOrigin = gatewayOrigin;
            state.parentOrigin = event.origin;
            state.instanceId = data.instanceId;
            state.moduleId = data.modId;
            state.userId = String(data.user?.id || 'local-user');
            state.grants = {
                permissions: Array.isArray(data.grants?.permissions) ? [...data.grants.permissions] : [],
                actions: Array.isArray(data.grants?.actions) ? [...data.grants.actions] : [],
            };
            state.connected = true;
            applyTheme(data.environment?.theme, data.appearance);
            window.parent.postMessage({
                type: 'vibedesk:ack',
                protocolVersion: '1.0',
                instanceId: state.instanceId,
                modId: state.moduleId,
            }, state.parentOrigin);
            notifyConfig();
            refreshAgentSettings();
            return;
        }

        if (data.type === 'vibedesk:action-result') {
            if (
                event.origin !== state.parentOrigin
                || data.instanceId !== state.instanceId
                || data.modId !== state.moduleId
            ) return;
            const pending = pendingActions.get(data.requestId);
            if (!pending || pending.actionId !== data.actionId) return;
            pendingActions.delete(data.requestId);
            window.clearTimeout(pending.timer);
            if (data.ok) {
                if (data.result?.id) {
                    activeTasks.set(data.result.id, {
                        id: data.result.id,
                        status: data.result.status || 'queued',
                        actionId: data.actionId,
                    });
                }
                pending.resolve(data.result);
            } else {
                pending.reject(new Error(data.error?.message || 'Newma-Desk Action failed'));
            }
            return;
        }

        if (data.type === 'vibedesk:context-request') {
            if (
                event.origin === state.parentOrigin
                && data.instanceId === state.instanceId
                && data.modId === state.moduleId
                && data.requestId
            ) publishContext(data.requestId);
            return;
        }

        if (data.type !== 'vibedesk:config') return;
        const gatewayOrigin = exactHttpOrigin(data.gatewayOrigin);
        if (!gatewayOrigin || gatewayOrigin !== event.origin) return;
        state.gatewayOrigin = gatewayOrigin;
        state.parentOrigin = event.origin;
        state.moduleId = typeof data.moduleId === 'string' && data.moduleId ? data.moduleId : deskModId;
        state.userId = typeof data.userId === 'string' && data.userId ? data.userId : 'local-user';
        applyTheme(data.theme, data.appearance);
        notifyConfig();
        refreshAgentSettings();
    });

    document.addEventListener('DOMContentLoaded', () => {
        activateEmbeddedModule();
        if (state.theme) applyTheme(state.theme, state.appearance);
        sendHello();
        sendReady();
        refreshAgentSettings();
    });
    window.addEventListener('load', sendReady);
})(window);
