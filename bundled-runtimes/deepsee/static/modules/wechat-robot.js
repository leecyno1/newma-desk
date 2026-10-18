/* One controller shared by the standalone page and Desk embed. */
(() => {
    const $ = id => document.getElementById(id);
    let loaded = false, dirty = false, loading = null, refreshing = false;
    let activityItems = [], activitySignature = '';
    const editor = $('wechat-trigger-rules');
    const note = text => { $('wechatTriggerRulesMsg').textContent = text; };
    function updateDraftState() {
        $('robotDraftState').textContent = dirty ? '● 未保存修改' : '已保存';
        $('robotDraftState').dataset.dirty = String(dirty);
    }
    function updateForm() {
        const fixed = $('robotReplyMode').value === 'fixed';
        $('robotFixedField').hidden = !fixed;
        $('robotAiField').hidden = fixed;
        const triggers = [$('wechatTriggerPrefixes').value.trim() && '前缀',
            $('wechatTriggerRegexpPatterns').value.trim() && '正则',
            $('wechatTriggerAtMentionEnabled').checked && '@ 我',
            Number($('wechatTriggerRandomRate').value) > 0 && '随机'].filter(Boolean);
        $('robotTriggerHint').textContent = triggers.length ? '当前入口：' + triggers.join(' / ') : '注意：没有设置触发条件，所有文字消息都可能触发。';
        $('robotTriggerHint').dataset.warning = String(!triggers.length);
        const days = [...$('robotActiveDays').querySelectorAll('input:checked')].map(el => el.nextElementSibling.textContent);
        const limited = $('robotScheduleEnabled').checked;
        const start = $('robotScheduleStart').value, end = $('robotScheduleEnd').value;
        $('robotScheduleStart').disabled = $('robotScheduleEnd').disabled = !limited;
        const period = !limited || start === end ? '全天' : `${start}–${end}${start > end ? '（跨午夜）' : ''}`;
        $('robotScheduleSummary').textContent = days.length ? `${days.length === 7 ? '每天' : days.join('、')} · ${period}` : '未选日期 · 自动回复暂停';
    }
    editor?.addEventListener('input', event => {
        if (event.target.closest('#robotPanelMemory')) return;
        dirty = true; updateDraftState(); updateForm();
        note('未保存；模拟使用当前编辑内容。');
    });
    const tabNames = {common:'Common', memory:'Memory'};
    function selectTab(name, focus = false) {
        if (!tabNames[name]) return;
        for (const [key, suffix] of Object.entries(tabNames)) {
            $('robotPanel' + suffix).hidden = key !== name;
            $('robotTab' + suffix).setAttribute('aria-selected', String(key === name));
            $('robotTab' + suffix).tabIndex = key === name ? 0 : -1;
        }
        editor.querySelector('.robot-config-body').scrollTop = 0;
        editor.querySelector('.robot-editor-footer').hidden = name === 'memory';
        if (focus) $('robotTab' + tabNames[name]).focus();
    }
    editor.querySelector('[role="tablist"]').addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const names = Object.keys(tabNames);
        const index = names.findIndex(name => $('robotTab' + tabNames[name]) === event.target);
        if (index < 0) return;
        event.preventDefault();
        selectTab(names[event.key === 'Home' ? 0 : event.key === 'End' ? names.length-1 : (index + (event.key === 'ArrowRight' ? 1 : names.length-1)) % names.length], true);
    });
    function settingsLoaded(config) {
        loaded = true; dirty = false;
        updateDraftState(); updateForm(); $('robotSave').disabled = false;
        note('修改后需保存；总开关立即生效。');
    }
    const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const fields = {
        reply_mode: ['robotReplyMode', 'value', 'ai'],
        delivery_mode: ['robotDeliveryMode', 'value', 'auto'],
        fixed_reply_text: ['robotFixedReply', 'value', ''],
        reply_system_prompt: ['robotSystemPrompt', 'value', ''],
        reply_agent_web_search: ['robotAgentWebSearch', 'checked', true],
        max_reply_chars: ['robotMaxChars', 'number', 0],
        group_require_mention: ['robotRequireMention', 'checked', false],
        schedule_enabled: ['robotScheduleEnabled', 'checked', false],
        schedule_start: ['robotScheduleStart', 'value', '09:00'],
        schedule_end: ['robotScheduleEnd', 'value', '18:00'],
        max_input_chars: ['robotMaxInput', 'number', 0],
        reply_cooldown_seconds: ['robotCooldown', 'number', 0],
        blocked_reply_keywords: ['robotBlockedReplyKeywords', 'lines', []],
        low_info_enabled: ['robotLowInfoEnabled', 'checked', true],
        low_info_emoji_enabled: ['robotLowInfoEmoji', 'checked', true],
        low_info_repeat_enabled: ['robotLowInfoRepeat', 'checked', true],
        low_info_min_repeats: ['robotLowInfoRepeats', 'number', 4],
        low_info_max_chars: ['robotLowInfoMaxChars', 'number', 80],
        low_info_repeat_units: ['robotLowInfoUnits', 'lines', []],
        low_info_emoji_names: ['robotLowInfoEmojiNames', 'lines', []],
        low_info_allow_texts: ['robotLowInfoAllow', 'lines', []],
        active_days: ['robotActiveDays', 'days', [0,1,2,3,4,5,6]],
    };
    const reasons = {
        passed: '命中规则', prefix_miss: '未命中触发前缀', regexp_miss: '未命中正则',
        at_mention_required: '没有 @ 本机', group_mention_required: '群聊强制要求 @ 本机',
        random_miss: '本次未命中随机触发', trigger_rules_disabled: '规则已暂停',
        smart_reply_disabled: '机器人已暂停', group_disabled: '群聊回复已关闭', private_disabled: '私聊回复已关闭',
        outside_schedule: '不在生效时段', input_keyword_blocked: '命中不回复关键词',
        chat_not_whitelisted: '会话不在白名单', chat_blacklisted: '会话在黑名单',
        sender_not_whitelisted: '发送者不在白名单', sender_blacklisted: '发送者在黑名单',
        text_too_short: '消息过短', human_reply_suppressed: '人工已接管',
        reply_too_long: '回复超过字数上限', empty_reply: '回复为空', preview_only: '仅预览，未发送',
        gateway_disabled: '网关未启用', outbound_disabled: '发送权限未启用',
        policy_changed_before_send: '发送前设置发生变化，已取消', sent: '已发送',
        gateway_not_configured: '微信设备尚未配置', keyword_blocked: '命中网关屏蔽词',
        inactive_day: '不在生效日期', input_too_long: '输入超过字数上限', reply_cooldown: '同会话回复冷却中',
        output_keyword_blocked: '回复命中禁词，已拦截',
        low_info_emoji: '低信息量：纯表情，跳过回复',
        low_info_repetition: '低信息量：重复笑声，跳过回复',
    };
    const reason = code => reasons[code] || code || '未知状态';
    function renderActivity() {
        const container = $('robotActivity');
        const expanded = new Set([...container.querySelectorAll('details[open]')].map(el => el.dataset.messageId));
        const scrollTop = container.scrollTop;
        const statusFilter = $('robotLogFilter').value;
        const query = $('robotLogSearch').value.trim().toLowerCase();
        const items = activityItems.filter(item => (!statusFilter || item.status === statusFilter)
            && (!query || [item.name, item.text, item.reply_preview, reason(item.reason)].join(' ').toLowerCase().includes(query)));
        $('robotActivityCount').textContent = `${items.length} / ${activityItems.length}`;
        container.innerHTML = items.length ? items.map(item => {
            const status = {sent:'已发送', blocked:'已拦截', failed:'失败', skipped:'已跳过', preview:'仅预览'}[item.status] || item.status;
            const date = new Date(item.updated_at);
            const time = Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('zh-CN', {hour12:false});
            return `<details class="robot-log" data-message-id="${escape(item.message_id)}" ${expanded.has(String(item.message_id)) ? 'open' : ''}>
                <summary><div class="robot-log-head"><strong>${escape(item.name || item.chat_id)}</strong><span class="robot-log-state" data-status="${escape(item.status)}">${escape(status)}</span><time>${escape(time)}</time></div>
                <span class="robot-log-preview">${escape(reason(item.reason))} · ${escape(item.text)}</span></summary>
                <div class="robot-log-detail"><small>${escape(item.updated_at)} · ${escape(reason(item.reason))}</small>${item.memory ? `<p class="robot-inline-hint">历史上下文：${Number(item.memory.messages) || 0} 条（对方 ${Number(item.memory.inbound) || 0} / 我方 ${Number(item.memory.outbound) || 0}）${item.memory.oldest_at ? ' · ' + escape(item.memory.oldest_at.replace('T', ' ')) + ' 起' : ''}${item.memory.truncated ? ' · 已按预算截取' : ''}</p>` : ''}<pre>${escape(item.text)}</pre>${item.reply_preview ? `<small>回复 / 预览</small><pre>${escape(item.reply_preview)}</pre>` : ''}</div></details>`;
        }).join('') : `<div class="robot-empty">${activityItems.length ? '没有符合条件的记录' : '暂无记录，等待新消息'}</div>`;
        container.scrollTop = scrollTop;
    }
    async function request(path, body) {
        const res = await fetch('/api/wechat-gateway/' + path, body === undefined ? {} : {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${res.status})`);
        return data;
    }
    $('robotAddPromptDefaults').onclick = async () => {
        const button = $('robotAddPromptDefaults');
        button.disabled = true;
        try {
            const {prompt} = await request('reply-prompt-template');
            const input = $('robotSystemPrompt');
            if (input.value.includes('【联系人与知识使用原则】')) {
                note('已包含此段原则，可直接编辑，无需重复添加。');
                return;
            }
            input.value = [input.value.trim(), prompt].filter(Boolean).join('\n\n');
            input.dispatchEvent(new Event('input', {bubbles: true}));
            note('已补入默认原则，保留原有要求；保存配置后生效。');
        } catch (error) { note('读取默认原则失败：' + error.message); }
        finally { button.disabled = false; }
    };
    function fillSettings(config) {
        for (const [key, [id, type, fallback]] of Object.entries(fields)) {
            const el = $(id);
            if (!el) continue;
            const value = config[key] ?? fallback;
            if (type === 'days') { el.querySelectorAll('input').forEach(o=>{o.checked=value.includes(Number(o.value));}); continue; }
            el[type === 'checked' ? 'checked' : 'value'] = type === 'lines' ? value.join('\n') : value;
        }
    }
    function readSettings() {
        const config = {};
        for (const [key, [id, type, fallback]] of Object.entries(fields)) {
            if (key === 'blocked_keywords') continue; // Saved only by blacklist management.
            const el = $(id);
            if (type === 'days') { config[key]=[...el.querySelectorAll('input:checked')].map(o=>Number(o.value)); continue; }
            const value = el ? el[type === 'checked' ? 'checked' : 'value'] : fallback;
            config[key] = type === 'number' ? Number(value) : type === 'lines'
                ? String(value).split(/\r?\n/).map(s => s.trim()).filter(Boolean) : value;
        }
        return config;
    }
    async function refresh() {
        if (refreshing) return;
        refreshing = true;
        try {
            const [rules, config, activity, device] = await Promise.all([
                request('trigger-rules'), request('config'), request('robot-activity'), request('device-status'),
            ]);
            const active = rules.enabled && rules.smart_reply_enabled && config.enabled && device.connected;
            const state = !(rules.enabled && rules.smart_reply_enabled) ? '自动回复已暂停'
                : !config.enabled ? '网关接收关闭 · 不会回复' : !device.connected ? '实时连接离线 · 等待恢复' : rules.delivery_mode === 'preview'
                ? '运行中 · 仅预览，不发送' : config.outbound_enabled ? '运行中 · 自动回复' : '发送权限关闭 · 不会发送';
            $('robotStatus').textContent = state;
            $('robotStatus').dataset.active = String(active);
            $('robotToggleLabel').textContent = rules.enabled && rules.smart_reply_enabled ? '自动回复 · 开' : '自动回复 · 关';
            $('robotToggle').setAttribute('aria-checked', String(!!(rules.enabled && rules.smart_reply_enabled)));
            $('robotToggle').dataset.running = String(rules.enabled && rules.smart_reply_enabled);
            $('robotToggle').disabled = false;
            const metrics = [
                ['连接', device.connected ? '在线' : '离线'],
                ['发送权限', config.outbound_enabled ? '已开' : '已关'],
                ['已保存', rules.reply_mode === 'fixed' ? '固定回复' : 'AI 回复'],
            ];
            $('robotMetrics').innerHTML = metrics.map(([label, value]) => `<div><span>${escape(label)}</span><strong>${escape(value)}</strong></div>`).join('');
            const signature = JSON.stringify(activity.items);
            if (signature !== activitySignature) {
                activityItems = activity.items; activitySignature = signature; renderActivity();
            }
            $('robotUpdatedAt').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', {hour12:false});
        } catch (error) {
            activitySignature = '';
            $('robotStatus').textContent = '读取失败：' + error.message;
            $('robotStatus').dataset.active = 'false';
            $('robotToggle').disabled = true;
            $('robotActivity').textContent = '暂时无法读取记录，请刷新重试。';
        } finally { refreshing = false; }
    }
    async function toggle(button) {
        button.disabled = true;
        try {
            const current = await request('trigger-rules');
            const enabling = !(current.enabled && current.smart_reply_enabled);
            if (enabling && dirty) throw new Error('请先保存或重载当前修改，再启用机器人。');
            if (enabling && !window.confirm('启用已保存的自动回复规则？自动发送模式下，新消息可能立即收到回复。')) return;
            await request('trigger-rules', enabling ? {enabled:true, smart_reply_enabled:true} : {smart_reply_enabled:false});
            if (!dirty) await loadWechatTriggerRules(true);
            else {
                $('wechatSmartReplyEnabled').checked = false;
                note('已立即暂停自动回复；其他未保存修改仍保留。');
            }
            await refresh();
        } catch (error) { $('robotStatus').textContent = '开关操作失败：' + error.message; }
        finally { button.disabled = false; }
    }
    async function activate() {
        if (!loaded && !loading) {
            loading = loadWechatTriggerRules(true).catch(error => { note('规则加载失败：' + error.message); }).finally(() => { loading = null; });
        }
        if (loading) await loading;
        await refresh();
    }
    async function reloadRules() {
        if (dirty && !window.confirm('重载将丢弃未保存的规则修改，继续吗？')) return;
        try { await loadWechatTriggerRules(true); await refresh(); }
        catch (error) { note('规则加载失败：' + error.message); }
    }
    async function saveRules(button) {
        if (!loaded) { note('请先成功加载规则，避免覆盖现有配置。'); return; }
        const invalid = [...$('robotPanelCommon').querySelectorAll('input,select,textarea')].find(el => !el.checkValidity());
        if (invalid) {
            const panel = invalid.closest('[data-robot-tab]');
            if (panel) selectTab(panel.dataset.robotTab);
            invalid.reportValidity(); return;
        }
        const controls = [...editor.querySelectorAll('input,select,textarea,button')].filter(el => !el.disabled);
        controls.forEach(el => { el.disabled = true; });
        button.disabled = true;
        try {
            const draft = readWechatTriggerRules();
            if (draft.enabled && draft.smart_reply_enabled && draft.delivery_mode === 'auto'
                && !window.confirm('保存后将按新规则自动回复。确认作用对象和触发范围正确吗？')) return;
            await saveWechatTriggerRules(true);
            await loadWechatTriggerRules(true);
            note('规则已保存并立即生效。');
            await refresh();
        } catch (error) { note('保存失败：' + error.message); }
        finally { controls.forEach(el => { el.disabled = false; }); updateForm(); }
    }
    async function simulate(button) {
        button.disabled = true;
        try {
            if (!loaded) throw new Error('规则尚未加载，请先重载规则。');
            const text = $('robotTestText').value.trim();
            if (!text) throw new Error('请先输入测试消息');
            const rules = readWechatTriggerRules();
            const asEnabled = $('robotTestAsEnabled').checked;
            if (asEnabled) Object.assign(rules, {enabled:true, smart_reply_enabled:true});
            const data = await request('robot-simulate', {
                chat_id: $('robotTestChat').value.trim(), sender_id: $('robotTestSender').value.trim(),
                text, mentioned: $('robotTestMentioned').checked, rules,
            });
            const lines = [data.allowed ? '通过 · ' + reason(data.reason) : '拦截 · ' + reason(data.reason)];
            if (asEnabled) lines.push('按启用后规则模拟，未更改实际开关。');
            $('robotTestResult').dataset.result = data.allowed ? 'passed' : 'blocked';
            if (data.matched_by) lines.push('触发入口：' + ({prefix:'前缀', regexp:'正则', at_mention:'@ 提及', random:'随机', always:'全部消息'}[data.matched_by] || data.matched_by));
            if (!data.gateway_enabled) lines.push('网关未启用，实际不会自动回复。');
            if (!data.outbound_enabled) lines.push('发送权限关闭。');
            if (data.rules.delivery_mode === 'preview') lines.push('当前仅生成预览，不发送。');
            if (data.reply_preview) lines.push('固定回复预览：' + data.reply_preview);
            else if (data.allowed) lines.push('实际回复将由 AI 生成；本次未调用 AI。');
            $('robotTestResult').textContent = lines.join('\n');
        } catch (error) { $('robotTestResult').textContent = error.message; $('robotTestResult').dataset.result = 'error'; }
        finally { button.disabled = false; }
    }
    // Use the actual header height: zoom and wrapped navigation change the available workspace.
    function resizeWorkspace() {
        const panel = $('send-management');
        if (!panel?.classList.contains('active')) return;
        const top = panel.getBoundingClientRect().top + window.scrollY;
        panel.style.setProperty('--wechat-workspace-height', Math.max(300, window.innerHeight - top) + 'px');
    }
    const layoutObserver = new ResizeObserver(resizeWorkspace);
    document.querySelectorAll('.header, .module-tabs').forEach(el => layoutObserver.observe(el));
    new MutationObserver(resizeWorkspace).observe($('send-management'), {attributes:true, attributeFilter:['class']});
    window.addEventListener('resize', resizeWorkspace);
    resizeWorkspace();
    setInterval(() => {
        if (!document.hidden && $('robotAutoRefresh').checked && $('wechat-automation')?.classList.contains('active')) refresh();
    }, 10000);
    window.WechatRobot = {fillSettings, readSettings, settingsLoaded, activate, refresh, toggle, simulate, saveRules, reloadRules, selectTab, renderActivity};
})();
