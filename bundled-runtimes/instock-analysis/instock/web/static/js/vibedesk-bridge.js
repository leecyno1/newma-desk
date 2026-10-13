(function () {
    'use strict';

    const script = document.currentScript;
    const modId = (script && script.dataset.modId || '').trim();
    const configuredOrigins = (script && script.dataset.parentOrigins || '')
        .split(',').map(value => value.trim().replace(/\/$/, '')).filter(Boolean);
    const embedded = window.parent !== window;
    const EVENT_CHANNEL = 'vibe-visualization-events';
    const eventChannel = !embedded && typeof window.BroadcastChannel === 'function'
        ? new window.BroadcastChannel(EVENT_CHANNEL)
        : null;
    let activeConfig = null;
    let contextProvider = null;
    let handoffHandler = null;
    let themeFallbackTimer = null;
    const queuedHandoffs = [];
    const pendingActions = new Map();
    const eventListeners = new Set();
    const eventTraceIds = new Set();
    const appliedAppearanceVariables = new Set();
    let readySettled = false;
    let resolveReady;
    const ready = new Promise(resolve => { resolveReady = resolve; });

    function settleReady() {
        if (readySettled) return;
        readySettled = true;
        resolveReady(Boolean(activeConfig));
    }

    if (embedded) {
        document.documentElement.classList.add('vibedesk-embedded', 'vibedesk-theme-pending');
    }

    function exactOrigin(value) {
        try {
            const parsed = new URL(value);
            if (!['http:', 'https:'].includes(parsed.protocol) || parsed.origin !== value.replace(/\/$/, '')) return '';
            return parsed.origin;
        } catch (_) {
            return '';
        }
    }

    const allowedOrigins = configuredOrigins.map(exactOrigin).filter(Boolean);
    let referrerOrigin = '';
    try { referrerOrigin = document.referrer ? new URL(document.referrer).origin : ''; } catch (_) { referrerOrigin = ''; }
    if (referrerOrigin === window.location.origin && !allowedOrigins.includes(referrerOrigin)) {
        allowedOrigins.push(referrerOrigin);
    }
    const parentOrigin = allowedOrigins.includes(referrerOrigin) ? referrerOrigin : (allowedOrigins[0] || '');

    function requestId() {
        return window.crypto && window.crypto.randomUUID
            ? window.crypto.randomUUID()
            : `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    function applyAppearance(appearance) {
        const cssVars = appearance && typeof appearance === 'object' && appearance.cssVars &&
            typeof appearance.cssVars === 'object' ? appearance.cssVars : {};
        const root = document.documentElement;
        const nextVariables = new Set();
        Object.entries(cssVars).forEach(([name, value]) => {
            if (!/^--[a-z0-9-]{2,80}$/.test(name) || typeof value !== 'string' || value.length > 200) return;
            root.style.setProperty(name, value);
            nextVariables.add(name);
        });
        appliedAppearanceVariables.forEach(name => {
            if (!nextVariables.has(name)) root.style.removeProperty(name);
        });
        appliedAppearanceVariables.clear();
        nextVariables.forEach(name => appliedAppearanceVariables.add(name));
    }

    function applyTheme(theme, source, appearance) {
        if (!['light', 'dark'].includes(theme)) return;
        const root = document.documentElement;
        const previous = root.dataset.vibedeskTheme || '';
        applyAppearance(appearance);
        root.dataset.vibedeskTheme = theme;
        root.dataset.theme = theme;
        root.dataset.bsTheme = theme;
        root.style.colorScheme = theme;
        root.classList.toggle('light', theme === 'light');
        root.classList.toggle('dark', theme === 'dark');
        root.classList.remove('vibedesk-theme-pending');
        document.dispatchEvent(new CustomEvent('instock:themechange', {
            detail: {theme, previous, source, appearance: appearance || null},
        }));
        window.dispatchEvent(new CustomEvent('newma:themechange', {
            detail: {mode: theme, appearance: appearance || null},
        }));
    }

    function applyEnvironment(environment, appearance) {
        if (!environment || typeof environment !== 'object') return;
        if (['light', 'dark'].includes(environment.theme)) {
            const compatibleAppearance = appearance && appearance.mode === environment.theme
                ? appearance
                : null;
            applyTheme(environment.theme, 'vibedesk:init', compatibleAppearance);
        }
        if (typeof environment.locale === 'string' && environment.locale.length >= 2) {
            document.documentElement.lang = environment.locale;
            document.documentElement.dataset.vibedeskLocale = environment.locale;
        }
        if (typeof environment.timezone === 'string' && environment.timezone) {
            document.documentElement.dataset.vibedeskTimezone = environment.timezone;
        }
    }

    function post(message) {
        if (!embedded || !parentOrigin) return false;
        window.parent.postMessage(message, parentOrigin);
        return true;
    }

    function validModEvent(data) {
        return data && data.version === '1.0' &&
            typeof data.event === 'string' && /^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/.test(data.event) &&
            typeof data.source === 'string' && typeof data.traceId === 'string' &&
            data.payload && typeof data.payload === 'object' && !Array.isArray(data.payload);
    }

    function deliverModEvent(data) {
        if (!validModEvent(data) || (data.target && data.target !== modId)) return false;
        if (eventTraceIds.has(data.traceId)) return false;
        eventTraceIds.add(data.traceId);
        if (eventTraceIds.size > 256) eventTraceIds.delete(eventTraceIds.values().next().value);
        eventListeners.forEach(listener => {
            try { listener(data); } catch (_) { /* one listener must not block the event seam */ }
        });
        return true;
    }

    function emitEvent(eventName, payload, target) {
        if (!/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/.test(eventName || '')) {
            throw new TypeError('event name must be namespaced');
        }
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            throw new TypeError('event payload must be an object');
        }
        const envelope = {
            version: '1.0',
            event: eventName,
            source: modId,
            ...(target ? {target} : {}),
            traceId: requestId(),
            payload,
        };
        if (embedded) return activeConfig && post(envelope) ? envelope : false;
        if (!eventChannel) return false;
        eventChannel.postMessage(envelope);
        return envelope;
    }

    function subscribeEvent(listener) {
        if (typeof listener !== 'function') throw new TypeError('event listener must be a function');
        eventListeners.add(listener);
        return function () { eventListeners.delete(listener); };
    }

    function validInit(data) {
        return data && data.type === 'vibedesk:init' && data.protocolVersion === '1.0' &&
            data.modId === modId && typeof data.instanceId === 'string' && data.instanceId.length > 0 &&
            data.environment && ['light', 'dark'].includes(data.environment.theme) &&
            typeof data.environment.locale === 'string' && typeof data.environment.timezone === 'string';
    }

    function compactText(value, limit) {
        return typeof value === 'string'
            ? value.replace(/\s+/g, ' ').trim().slice(0, limit)
            : '';
    }

    function isRecord(value) {
        return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
    }

    function visiblePageContext() {
        const contentRoot = document.querySelector('main')
            || document.querySelector('.main-content')
            || document.body;
        const title = compactText(
            contentRoot && contentRoot.querySelector('h1')?.textContent || document.title || modId,
            160,
        ) || modId;
        const viewId = compactText(`${modId}:${window.location.pathname}`.replace(/[^a-zA-Z0-9:_-]+/g, '-'), 128)
            || modId;
        const visibleBlocks = contentRoot
            ? Array.from(contentRoot.querySelectorAll('h1, h2, h3, [role="heading"]'))
                .map((heading, index) => ({
                    id: compactText(heading.id || `${viewId}-heading-${index + 1}`, 128),
                    type: heading.tagName.toLowerCase().slice(0, 80),
                    title: compactText(heading.textContent, 160),
                }))
                .filter(block => block.title)
                .slice(0, 80)
            : [];
        let renderedHtml = '';
        if (contentRoot) {
            const clone = contentRoot.cloneNode(true);
            clone.querySelectorAll('script, style, noscript, template, svg, canvas, input[type="password"], input[type="hidden"]')
                .forEach(element => element.remove());
            clone.querySelectorAll('[style]').forEach(element => element.removeAttribute('style'));
            renderedHtml = compactText(clone.outerHTML, 24000);
        }
        return {
            view: {id: viewId, title},
            visibleBlocks,
            selection: {
                location: compactText(
                    `${window.location.pathname}${window.location.search}${window.location.hash}`,
                    1000,
                ),
            },
            filters: {},
            data: {
                source: 'instock-rendered-dom',
                freshness: 'unknown',
                summary: {
                    contextSource: 'dom-html-fallback',
                    visibleText: compactText(contentRoot && contentRoot.innerText, 16000),
                    renderedHtml,
                    warning: '这是当前已渲染页面的 DOM/HTML 兜底，不是 Manifest，也不等同于结构化业务数据。',
                },
            },
            actions: grantedActions().map(id => ({id, available: true})),
            tasks: [],
        };
    }

    function normalizePageContext(candidate) {
        if (!isRecord(candidate) || !isRecord(candidate.view)) return visiblePageContext();
        const viewId = compactText(candidate.view.id, 128) || modId;
        const viewTitle = compactText(candidate.view.title, 160)
            || compactText(document.title, 160)
            || modId;
        const visibleBlocks = Array.isArray(candidate.visibleBlocks)
            ? candidate.visibleBlocks.flatMap((block, index) => {
                if (!isRecord(block)) return [];
                const title = compactText(block.title, 160);
                return [{
                    id: compactText(block.id, 128) || `${viewId}-block-${index + 1}`,
                    type: compactText(block.type, 80) || 'section',
                    ...(title ? {title} : {}),
                }];
            }).slice(0, 500)
            : [];
        const selection = isRecord(candidate.selection)
            ? candidate.selection
            : isRecord(candidate.selectedSecurity)
                ? {security: candidate.selectedSecurity}
                : {};
        const filters = isRecord(candidate.filters) ? candidate.filters : {};
        const rawData = isRecord(candidate.data) ? candidate.data : {};
        const freshness = ['live', 'fresh', 'stale', 'unknown'].includes(rawData.freshness)
            ? rawData.freshness
            : 'unknown';
        const officialDataKeys = new Set(['asOf', 'source', 'freshness', 'summary']);
        const isOfficialData = Object.keys(rawData).every(key => officialDataKeys.has(key))
            && (rawData.summary === undefined || isRecord(rawData.summary));
        const data = {
            ...(typeof rawData.asOf === 'string' ? {asOf: compactText(rawData.asOf, 80)} : {}),
            source: typeof rawData.source === 'string'
                ? compactText(rawData.source, 160)
                : 'instock-page-context',
            freshness,
            summary: isOfficialData
                ? (isRecord(rawData.summary) ? rawData.summary : {})
                : {contextSource: 'legacy-context-normalized', ...rawData},
        };
        const actions = Array.isArray(candidate.actions)
            ? candidate.actions.flatMap(action => {
                if (!isRecord(action) || typeof action.id !== 'string'
                    || !/^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/.test(action.id)) return [];
                const label = compactText(action.label, 160);
                return [{
                    id: action.id,
                    ...(label ? {label} : {}),
                    available: action.available !== false,
                    ...(action.inputSchema === undefined ? {} : {inputSchema: action.inputSchema}),
                }];
            }).slice(0, 500)
            : [];
        const tasks = Array.isArray(candidate.tasks)
            ? candidate.tasks.flatMap(task => {
                if (!isRecord(task)) return [];
                const id = compactText(task.id, 160);
                const status = compactText(task.status, 80);
                if (!id || !status) return [];
                return [{
                    id,
                    status,
                    ...(typeof task.actionId === 'string'
                        && /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/.test(task.actionId)
                        ? {actionId: task.actionId}
                        : {}),
                }];
            }).slice(0, 200)
            : [];
        return {
            view: {id: viewId, title: viewTitle},
            visibleBlocks,
            selection,
            filters,
            data,
            actions,
            tasks,
        };
    }

    async function publishContext(linkedRequestId) {
        if (!activeConfig) return false;
        try {
            const context = typeof contextProvider === 'function'
                ? normalizePageContext(await contextProvider())
                : visiblePageContext();
            return post({
                type: 'vibedesk:context',
                requestId: linkedRequestId || requestId(),
                instanceId: activeConfig.instanceId,
                modId,
                context,
            });
        } catch (_) {
            return post({
                type: 'vibedesk:context',
                requestId: linkedRequestId || requestId(),
                instanceId: activeConfig.instanceId,
                modId,
                context: visiblePageContext(),
            });
        }
    }

    function grantedActions() {
        const grants = activeConfig && activeConfig.grants;
        return grants && Array.isArray(grants.actions) ? grants.actions : [];
    }

    function canInvokeAction(actionId) {
        return Boolean(activeConfig && grantedActions().includes(actionId));
    }

    function invokeAction(actionId, input) {
        if (!canInvokeAction(actionId)) {
            return Promise.reject(new Error(`Newma-Desk 未授权 Action: ${actionId}`));
        }
        const id = requestId();
        return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
                pendingActions.delete(id);
                reject(new Error(`Newma-Desk Action 超时: ${actionId}`));
            }, 35000);
            pendingActions.set(id, {actionId, resolve, reject, timer});
            if (!post({
                type: 'vibedesk:action-request',
                requestId: id,
                instanceId: activeConfig.instanceId,
                modId,
                actionId,
                input: input && typeof input === 'object' ? input : {},
            })) {
                window.clearTimeout(timer);
                pendingActions.delete(id);
                reject(new Error('Newma-Desk 宿主不可用'));
            }
        });
    }

    function deliverHandoff(data) {
        if (!activeConfig || !data || data.type !== 'vibedesk:handoff') return;
        if (data.modId !== modId || data.instanceId !== activeConfig.instanceId) return;
        if (!data.handoff || data.handoff.targetModId !== modId || typeof data.handoff.id !== 'string') return;
        if (typeof handoffHandler !== 'function') {
            queuedHandoffs.push(data);
            return;
        }
        Promise.resolve(handoffHandler(data.handoff)).then(
            result => post({
                type: 'vibedesk:handoff-result',
                requestId: data.requestId,
                instanceId: activeConfig.instanceId,
                modId,
                handoffId: data.handoff.id,
                ok: true,
                result: result == null ? {} : result,
            }),
            reason => post({
                type: 'vibedesk:handoff-result',
                requestId: data.requestId,
                instanceId: activeConfig.instanceId,
                modId,
                handoffId: data.handoff.id,
                ok: false,
                error: {
                    code: 'handoff_failed',
                    message: reason instanceof Error ? reason.message : 'Wiki 交接失败',
                },
            }),
        );
    }

    function handleMessage(event) {
        if (event.source !== window.parent || event.origin !== parentOrigin) return;
        const data = event.data;
        if (validInit(data)) {
            activeConfig = data;
            if (themeFallbackTimer !== null) {
                window.clearTimeout(themeFallbackTimer);
                themeFallbackTimer = null;
            }
            settleReady();
            applyEnvironment(data.environment, data.appearance);
            post({
                type: 'vibedesk:ack',
                protocolVersion: '1.0',
                instanceId: data.instanceId,
                modId,
            });
            document.dispatchEvent(new CustomEvent('vibedesk:init', {detail: data}));
            return;
        }
        if (activeConfig && validModEvent(data)) {
            deliverModEvent(data);
            return;
        }
        if (activeConfig && data && data.type === 'vibedesk:action-result') {
            if (data.modId !== modId || data.instanceId !== activeConfig.instanceId) return;
            const pending = pendingActions.get(data.requestId);
            if (!pending || data.actionId !== pending.actionId) return;
            pendingActions.delete(data.requestId);
            window.clearTimeout(pending.timer);
            if (data.ok === true) pending.resolve(data.result);
            else {
                const message = data.error && data.error.message ? data.error.message : 'Newma-Desk Action 执行失败';
                pending.reject(new Error(message));
            }
            return;
        }
        if (activeConfig && data && data.type === 'vibedesk:handoff') {
            deliverHandoff(data);
            return;
        }
        if (!activeConfig || !data || data.type !== 'vibedesk:context-request') return;
        if (data.modId !== modId || data.instanceId !== activeConfig.instanceId) return;
        if (typeof data.requestId !== 'string' || !['initial', 'agent', 'refresh'].includes(data.reason)) return;
        publishContext(data.requestId);
    }

    const bridge = {
        embedded,
        get connected() { return Boolean(activeConfig); },
        get config() { return activeConfig; },
        get theme() { return document.documentElement.dataset.vibedeskTheme || 'light'; },
        whenReady() { return ready; },
        canInvokeAction,
        invokeAction,
        emit: emitEvent,
        subscribe: subscribeEvent,
        setContextProvider(provider) {
            if (typeof provider !== 'function') throw new TypeError('context provider must be a function');
            contextProvider = provider;
            return function () { if (contextProvider === provider) contextProvider = null; };
        },
        setHandoffHandler(handler) {
            if (typeof handler !== 'function') throw new TypeError('handoff handler must be a function');
            handoffHandler = handler;
            while (activeConfig && queuedHandoffs.length) deliverHandoff(queuedHandoffs.shift());
            return function () { if (handoffHandler === handler) handoffHandler = null; };
        },
        publishContext: function () { return publishContext(); },
    };
    window.InStockNewmaDesk = bridge;
    window.InStockVibeDesk = bridge;

    if (eventChannel) {
        eventChannel.addEventListener('message', event => deliverModEvent(event.data));
    }

    if (!embedded) {
        applyTheme('light', 'standalone');
        settleReady();
        return;
    }
    themeFallbackTimer = window.setTimeout(() => {
        themeFallbackTimer = null;
        if (!activeConfig) applyTheme('light', 'standalone-fallback');
        settleReady();
    }, 1500);
    const style = document.createElement('style');
    style.textContent = [
        'html.vibedesk-embedded #sidebar, html.vibedesk-embedded #navbar { display: none !important; }',
        'html.vibedesk-embedded .main-content { margin-left: 0 !important; }',
        'html.vibedesk-embedded .main-container, html.vibedesk-embedded .main-content, html.vibedesk-embedded .main-content-inner { width: 100% !important; }',
    ].join('\n');
    document.head.appendChild(style);

    if (!modId || !parentOrigin) {
        console.warn('Newma-Desk Bridge 未启动：请配置精确的 INSTOCK_EMBED_ORIGINS');
        return;
    }
    window.addEventListener('message', handleMessage);
    post({
        type: 'vibedesk:hello',
        modId,
        protocolVersions: ['1.0'],
        sdkVersion: 'instock-bridge-1.0.0',
        capabilities: ['actions', 'data', 'context', 'theme', 'handoff'],
    });
})();
