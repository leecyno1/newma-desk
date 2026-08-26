(function initWechatSyncModule(window) {
    'use strict';

    const TRACK_DEFS = Object.freeze([
        Object.freeze({ key: 'wechatapi', label: 'WeChat API', kind: '云端实时回调' }),
        Object.freeze({ key: 'chatlog', label: 'chatlog_alpha', kind: '本地历史补齐' }),
        Object.freeze({ key: 'wx_cli', label: 'wx-cli', kind: '本地 CLI 读取' }),
    ]);
    let trackOrder = TRACK_DEFS.map(item => item.key);
    let enabledTracks = new Set(trackOrder);
    let useMultipleTracks = false;

    function getDocument() {
        if (!window.document) throw new Error('WechatSyncModule requires window.document');
        return window.document;
    }

    function getHelper(name) {
        const helper = window[name];
        if (typeof helper !== 'function') {
            throw new Error(`WechatSyncModule requires window.${name}`);
        }
        return helper;
    }

    function callHelper(name, ...args) {
        return getHelper(name).apply(window, args);
    }

    function fallbackEscapeHtml(value) {
        const replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        };
        return String(value ?? '').replace(/[&<>"']/g, char => replacements[char]);
    }

    function escapeHtml(value) {
        const helper = window.escapeHtml;
        return typeof helper === 'function'
            ? helper.call(window, value)
            : fallbackEscapeHtml(value);
    }

    function normalizeTrackPolicy(policy = {}) {
        const valid = TRACK_DEFS.map(item => item.key);
        const legacyMode = String(policy.mode || '').trim();
        let order = Array.isArray(policy.track_order) ? policy.track_order.map(String) : [];
        let enabled = Array.isArray(policy.enabled_tracks) ? policy.enabled_tracks.map(String) : [];
        const useMultiple = !!policy.use_multiple_tracks;
        if (!order.length && legacyMode === 'chatlog_only') order = ['chatlog', 'wx_cli', 'wechatapi'];
        if (!enabled.length && legacyMode === 'chatlog_only') enabled = ['chatlog', 'wx_cli'];
        if (!order.length && legacyMode === 'wechatapi_only') order = ['wechatapi', 'chatlog', 'wx_cli'];
        if (!enabled.length && legacyMode === 'wechatapi_only') enabled = ['wechatapi'];
        if (!order.length) order = ['wechatapi', 'chatlog', 'wx_cli'];
        if (!enabled.length) enabled = ['wechatapi', 'chatlog', 'wx_cli'];
        order = order.filter((item, idx) => valid.includes(item) && order.indexOf(item) === idx);
        valid.forEach(item => { if (!order.includes(item)) order.push(item); });
        enabled = enabled.filter((item, idx) => valid.includes(item) && enabled.indexOf(item) === idx);
        if (!enabled.length) enabled = [order[0] || 'wechatapi'];
        return { order, enabled, useMultiple };
    }

    function renderTrackOrder(policy = {}) {
        const document = getDocument();
        const list = document.getElementById('wechatTrackOrderList');
        if (!list) return;
        const normalized = normalizeTrackPolicy(policy);
        trackOrder = normalized.order;
        enabledTracks = new Set(normalized.enabled);
        useMultipleTracks = !!normalized.useMultiple;
        const multi = document.getElementById('wechatUseMultipleTracks');
        if (multi) multi.checked = useMultipleTracks;
        list.innerHTML = '';
        trackOrder.forEach((track, idx) => {
            const def = TRACK_DEFS.find(item => item.key === track) || { key: track, label: track, kind: '' };
            const enabled = enabledTracks.has(track);
            const row = document.createElement('div');
            row.className = `wechat-track-row${enabled ? '' : ' is-disabled'}`;
            row.dataset.track = track;
            row.draggable = true;
            row.innerHTML = `
                <div class="wechat-track-rank">${idx + 1}</div>
                <label class="wechat-track-main">
                    <input type="checkbox" data-wechat-track-enabled="${track}" ${enabled ? 'checked' : ''}>
                    <span style="min-width:0;">
                        <span class="wechat-track-name">${escapeHtml(def.label)}</span>
                        <span class="wechat-track-kind">${escapeHtml(def.kind)}</span>
                    </span>
                </label>
                <div class="wechat-track-actions">
                    <button type="button" class="test-btn" data-track-move="${track}" data-delta="-1" title="上移">↑</button>
                    <button type="button" class="test-btn" data-track-move="${track}" data-delta="1" title="下移">↓</button>
                </div>`;
            row.addEventListener('dragstart', (ev) => {
                row.classList.add('is-dragging');
                ev.dataTransfer?.setData('text/plain', track);
            });
            row.addEventListener('dragend', () => row.classList.remove('is-dragging'));
            row.addEventListener('dragover', (ev) => ev.preventDefault());
            row.addEventListener('drop', (ev) => {
                ev.preventDefault();
                const fromTrack = ev.dataTransfer?.getData('text/plain') || '';
                moveTrackBefore(fromTrack, track);
            });
            list.appendChild(row);
        });
        list.querySelectorAll('[data-wechat-track-enabled]').forEach(input => {
            input.addEventListener('change', () => {
                const checked = Array.from(list.querySelectorAll('[data-wechat-track-enabled]'))
                    .filter(el => el.checked);
                if (!checked.length) input.checked = true;
                updateTrackPolicySummary();
                renderTrackOrder(collectTrackPolicy());
            });
        });
        list.querySelectorAll('[data-track-move]').forEach(btn => {
            btn.addEventListener('click', () => {
                moveTrack(btn.dataset.track, parseInt(btn.dataset.delta || '0', 10));
            });
        });
        if (multi && !multi.dataset.boundWechatMulti) {
            multi.dataset.boundWechatMulti = '1';
            multi.addEventListener('change', updateTrackPolicySummary);
        }
        updateTrackPolicySummary();
    }

    function collectTrackPolicy() {
        const document = getDocument();
        const list = document.getElementById('wechatTrackOrderList');
        const order = Array.from(list?.querySelectorAll('.wechat-track-row') || [])
            .map(row => row.dataset.track)
            .filter(Boolean);
        let enabled = Array.from(list?.querySelectorAll('[data-wechat-track-enabled]') || [])
            .filter(input => input.checked)
            .map(input => input.dataset.wechatTrackEnabled)
            .filter(Boolean);
        if (!enabled.length && order.length) enabled = [order[0]];
        return {
            track_order: order.length ? order : [...trackOrder],
            enabled_tracks: enabled,
            use_multiple_tracks: !!document.getElementById('wechatUseMultipleTracks')?.checked,
        };
    }

    function updateTrackPolicySummary() {
        const document = getDocument();
        const el = document.getElementById('wechatTrackPolicySummary');
        if (!el) return;
        const policy = collectTrackPolicy();
        const labels = policy.track_order
            .filter(track => policy.enabled_tracks.includes(track))
            .map(track => (TRACK_DEFS.find(item => item.key === track) || {}).label || track);
        if (!labels.length) {
            el.textContent = '未启用链路';
        } else if (policy.use_multiple_tracks && labels.length > 1) {
            el.textContent = `多链路补齐：${labels.join(' → ')}`;
        } else {
            el.textContent = `当前手动拉取链路：${labels[0]}`;
        }
    }

    function moveTrack(track, delta) {
        const policy = collectTrackPolicy();
        const order = policy.track_order;
        const from = order.indexOf(track);
        const to = from + Number(delta || 0);
        if (from < 0 || to < 0 || to >= order.length) return;
        order.splice(from, 1);
        order.splice(to, 0, track);
        renderTrackOrder({ track_order: order, enabled_tracks: policy.enabled_tracks });
    }

    function moveTrackBefore(fromTrack, toTrack) {
        if (!fromTrack || !toTrack || fromTrack === toTrack) return;
        const policy = collectTrackPolicy();
        const order = policy.track_order.filter(track => track !== fromTrack);
        const to = order.indexOf(toTrack);
        if (to < 0) return;
        order.splice(to, 0, fromTrack);
        renderTrackOrder({ track_order: order, enabled_tracks: policy.enabled_tracks });
    }

    function renderDualTrackState(data) {
        const document = getDocument();
        const policy = data?.policy || {};
        const tracks = data?.tracks || {};
        const api = tracks.wechatapi || {};
        const chatlog = tracks.chatlog || {};
        const wxCli = tracks.wx_cli || {};
        const apiEl = document.getElementById('wechatApiTrackStatus');
        const chatlogEl = document.getElementById('chatlogTrackStatus');
        const wxCliEl = document.getElementById('wxCliTrackStatus');
        const syncEl = document.getElementById('syncStatus');
        renderTrackOrder(policy);
        const badge = (ok) => ok ? '🟢' : '🔴';
        if (apiEl) apiEl.textContent = `${badge(api.healthy)} ${api.message || (api.configured ? '已配置' : '未配置')}`;
        if (chatlogEl) chatlogEl.textContent = `${badge(chatlog.healthy)} ${chatlog.message || '未检测'}`;
        if (wxCliEl) wxCliEl.textContent = `${badge(wxCli.healthy)} ${wxCli.message || '未检测'}`;
        if (syncEl && data?.active_track) syncEl.textContent = `当前轨道：${data.active_track}`;
    }

    async function loadDualTrackState(silent = false) {
        const document = getDocument();
        try {
            const data = await callHelper('requestJson', '/api/sync/wechat/dual-track/state');
            renderDualTrackState(data);
            return data;
        } catch (e) {
            if (!silent) {
                const syncEl = document.getElementById('syncStatus');
                if (syncEl) syncEl.textContent = `三轨状态读取失败：${e?.message || e}`;
            }
            throw e;
        }
    }

    async function saveDualTrackPolicy() {
        const document = getDocument();
        const syncEl = document.getElementById('syncStatus');
        const days = parseInt(document.getElementById('syncDays')?.value || '1', 10) || 1;
        const selection = collectTrackPolicy();
        const payload = {
            mode: 'custom',
            enabled_tracks: selection.enabled_tracks,
            track_order: selection.track_order,
            use_multiple_tracks: !!selection.use_multiple_tracks,
            chatlog_window_days: Math.max(1, Math.min(90, days)),
        };
        try {
            if (syncEl) syncEl.textContent = '保存三轨策略…';
            const res = await callHelper('requestJson', '/api/sync/wechat/dual-track/policy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (syncEl) syncEl.textContent = '三轨策略已保存';
            await loadDualTrackState(true);
            return res.policy || payload;
        } catch (e) {
            if (syncEl) syncEl.textContent = `保存失败：${e?.message || e}`;
            throw e;
        }
    }

    async function runDualTrackSync(days) {
        const document = getDocument();
        const syncEl = document.getElementById('syncStatus');
        const n = Math.max(
            1,
            Math.min(90, parseInt(days || document.getElementById('syncDays')?.value || '1', 10) || 1),
        );
        const op = callHelper('ensurePullOperation', null, `微信三轨同步近${n}天...`);
        if (!op) {
            if (syncEl) syncEl.textContent = '有任务正在执行';
            return;
        }
        try {
            if (syncEl) syncEl.textContent = '三轨同步中…';
            await saveDualTrackPolicy();
            const res = await callHelper(
                'fetchWithPullControl',
                `/api/sync/wechat/dual-track?days=${n}`,
                { method: 'POST' },
                op,
                90000,
            );
            const data = await res.json();
            renderDualTrackState(data);
            const actions = Array.isArray(data.actions) ? data.actions : [];
            const fetched = actions.reduce((sum, item) => sum + Number(item.fetched || 0), 0);
            const inserted = actions.reduce((sum, item) => sum + Number(item.inserted || 0), 0);
            const okTracks = actions.filter(item => item.status === 'ok').map(item => item.track).join(' → ');
            if (syncEl) syncEl.textContent = data.status === 'ok'
                ? `同步完成：${okTracks || '已检查'}，fetched=${fetched}, inserted=${inserted}`
                : `三轨异常：${actions.map(x => x.reason).filter(Boolean).join('；') || '请检查配置'}`;
            try {
                await callHelper('loadRecentMessagesFromBackend', n, false, op);
            } catch (_) { }
        } catch (e) {
            if (callHelper('isPullAbortError', e)) {
                if (syncEl) syncEl.textContent = '已取消';
            } else if (syncEl) {
                syncEl.textContent = `三轨同步失败：${e?.message || e}`;
            }
        } finally {
            callHelper('finishPullOperation', op);
        }
    }

    async function syncIncrementalAndReload(days = 7, pullOp = null) {
        const document = getDocument();
        const ownOp = !pullOp;
        const fullDays = Math.max(1, days || 7);
        const op = callHelper('ensurePullOperation', pullOp, `微信同步近${fullDays}天...`);
        if (!op) return;
        try {
            callHelper('throwIfPullAborted', op);
            const statusEl = document.getElementById('loadingStatus');
            if (statusEl) statusEl.textContent = `微信同步近${fullDays}天...`;
            const resp = await callHelper(
                'fetchWithPullControl',
                `/api/sync/wechat/dual-track?days=${fullDays}`,
                { method: 'POST' },
                op,
                120000,
            );
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || data.status === 'error') {
                const actions = Array.isArray(data.actions) ? data.actions : [];
                const reason = actions.map(x => x.reason).filter(Boolean).join('；') || `HTTP ${resp.status}`;
                throw new Error(reason);
            }
            try {
                renderDualTrackState(data);
            } catch (_) { }
            const actions = Array.isArray(data.actions) ? data.actions : [];
            const okAction = actions.find(item => item.status === 'ok') || {};
            if (statusEl) statusEl.textContent = `${okAction.track || '微信'}同步完成，刷新列表...`;
            await callHelper('loadRecentMessagesFromBackend', fullDays, false, op);
            try {
                const renderDashboard = window.renderDashboard;
                if (typeof renderDashboard === 'function') renderDashboard.call(window);
            } catch (_) { }
            try {
                const now2 = new Date();
                const since2 = new Date(now2.getTime() - fullDays * 24 * 60 * 60 * 1000).toISOString();
                await callHelper('runAutoDeriveForWindow', since2, now2.toISOString(), op);
                await callHelper('loadRecentMessagesFromBackend', fullDays, false, op);
            } catch (e) {
                if (!callHelper('isPullAbortError', e)) window.console?.warn('自动派生失败:', e);
            }
            try {
                callHelper('resetMessageFiltersToDefault');
            } catch (_) { }
            try {
                callHelper('applyNoSpamDefault', 'all');
            } catch (_) { }
            if (statusEl) {
                statusEl.textContent = '完成';
                window.setTimeout(() => {
                    const ss = getDocument().getElementById('loadingStatus');
                    if (ss) ss.textContent = '';
                }, 1500);
            }
        } catch (e) {
            if (callHelper('isPullAbortError', e)) {
                try {
                    const status = document.getElementById('loadingStatus');
                    if (status) status.textContent = '已取消';
                } catch (_) { }
                return;
            }
            window.console?.error('微信三轨同步失败:', e);
            callHelper(
                'showMessageTableError',
                `微信同步失败：${e?.message || e}。云端请检查 WeChat API；本地版请启动 chatlog_alpha 或 wx-cli。`,
            );
        } finally {
            if (ownOp) callHelper('finishPullOperation', op);
        }
    }

    window.WechatSyncModule = Object.freeze({
        normalizeTrackPolicy,
        renderTrackOrder,
        collectTrackPolicy,
        updateTrackPolicySummary,
        moveTrack,
        moveTrackBefore,
        renderDualTrackState,
        loadDualTrackState,
        saveDualTrackPolicy,
        runDualTrackSync,
        syncIncrementalAndReload,
    });
})(window);
