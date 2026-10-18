/* Database-backed historical search, shared by standalone and Desk embeds. */
(() => {
    const types = {text: '文字', image: '图片', link: '链接', file: '文件', voice: '语音', video: '视频', emoji: '表情', system: '系统'};
    let dialog, page = 1, controller, lastQuery, previewUrl, previewController;
    const get = id => dialog.querySelector(`#${id}`);
    const dateString = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const httpUrl = value => {
        try { const url = new URL(String(value || '')); return /https?:/.test(url.protocol) ? url.href : ''; }
        catch (_) { return ''; }
    };
    function node(tag, text) { const el = document.createElement(tag); if (text) el.textContent = text; return el; }
    function clearPreview() {
        previewController?.abort(); previewController = null;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = null;
        get('historyPreview').replaceChildren();
    }
    async function preview(message) {
        clearPreview();
        const box = get('historyPreview');
        box.textContent = '正在读取本地媒体…';
        const url = `/api/messages/media/${message.type === 'image' ? 'image' : 'local'}?message_id=${message.id}`;
        if (!url) { box.textContent = '此记录未保留可访问的媒体地址。'; return; }
        const request = previewController = new AbortController();
        try {
            const response = await fetch(url, {signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)])});
            if (!response.ok) throw new Error('missing');
            const blob = await response.blob();
            if (!/^(image|audio|video)\//.test(blob.type)) throw new Error('format');
            if (previewController !== request || !dialog.open) return;
            clearPreview();
            previewUrl = URL.createObjectURL(blob);
            const tag = blob.type.startsWith('image/') ? 'img' : blob.type.startsWith('audio/') ? 'audio' : 'video';
            const media = node(tag);
            media.src = previewUrl;
            media.style.cssText = 'max-width:100%;max-height:380px;display:block';
            media.controls = true;
            media.alt = '历史消息图片';
            box.append(media);
            if (message.type === 'video' && tag === 'img') box.append(node('p', '本地只保留了视频封面，原视频未留存。'));
        } catch (_) {
            if (previewController === request) box.textContent = '本地媒体暂不可用：可能未下载、已清理，或 Chatlog 服务不可用。聊天文字仍已保留。';
        }
    }
    function render(messages) {
        const body = get('historyRows');
        body.replaceChildren();
        for (const message of messages) {
            const row = node('tr');
            row.dataset.messageId = message.id;
            const time = String(message.timestamp || '').replace('T', ' ').slice(0, 19);
            for (const text of [time, message.sender_name || message.sender_id, message.talker_name || message.chat_id,
                               `${message.direction === 'out' ? '发出' : '收到'} · ${types[message.type] || message.type}`]) {
                row.append(node('td', text));
            }
            const content = node('td');
            const details = node('details');
            const text = message.content_text || '';
            // Protocol payloads are not readable text; media controls provide the useful view.
            const protocolPayload = /<(\?xml|msg|img|appmsg)\b/i.test(text) || /^!\[[^\]]*\]\(https?:\/\/.*\)$/s.test(text);
            const readable = protocolPayload ? `[${types[message.type] || '媒体'}]` : text;
            details.append(node('summary', message.type === 'system' ? '系统记录（展开查看）' : readable.slice(0, 180) || '无文字'));
            const full = node('pre', readable);
            full.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font:inherit';
            details.append(full);
            content.append(details);
            if (['image', 'voice', 'video', 'emoji'].includes(message.type)) {
                const button = node('button', message.type === 'image' ? '查看图片' : message.type === 'voice' ? '播放语音' : message.type === 'emoji' ? '查看表情' : '查看视频/封面');
                button.className = 'pagination-btn';
                button.onclick = () => preview(message);
                content.append(button);
            } else if (message.type === 'file') {
                const link = node('a', '打开文件');
                link.href = `/api/messages/media/file?message_id=${message.id}`;
                link.target = '_blank'; link.rel = 'noopener noreferrer';
                content.append(link);
            }
            const urls = new Set([message.type === 'link' ? httpUrl(message.media_url) : '',
                ...Array.from((protocolPayload ? '' : text).matchAll(/https?:\/\/[^\s<>"，。；]+/g), m => httpUrl(m[0]))].filter(Boolean));
            for (const url of [...urls].slice(0, 5)) {
                const link = node('a', '打开消息链接');
                link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
                link.style.marginLeft = '8px'; content.append(link);
            }
            row.append(content); body.append(row);
        }
    }
    async function search(nextPage = 1) {
        clearPreview();
        controller?.abort(); controller = new AbortController();
        const currentController = controller;
        const from = get('historyFrom').value, to = get('historyTo').value;
        if (from && to && from > to) { get('historyStatus').textContent = '开始日期不能晚于结束日期'; return; }
        const params = new URLSearchParams({page: String(nextPage), size: '50', search_mode: 'contains',
            include_mp_messages: 'true', exclude_system_messages: String(get('historyType').value !== 'system'), content_max_chars: '20000'});
        const keyword = get('historyQuery').value.trim();
        if (keyword) params.set('q', keyword);
        if (from) params.set('time_from', `${from}T00:00:00`);
        if (to) params.set('time_to', `${to}T23:59:59`);
        if (get('historyType').value) params.set('msg_type', get('historyType').value);
        if (get('historyDirection').value) params.set('direction', get('historyDirection').value);
        get('historyStatus').textContent = '正在检索本地记录…';
        get('historyPrev').disabled = get('historyNext').disabled = true;
        try {
            const response = await fetch(`/api/messages?${params}`, {signal: currentController.signal});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const result = await response.json();
            if (controller !== currentController || !dialog.open) return;
            page = nextPage; lastQuery = params.toString();
            render(result.items || []);
            get('historyStatus').textContent = `共 ${result.total} 条 · 第 ${page} / ${Math.max(1, Math.ceil(result.total / 50))} 页`;
            get('historyPrev').disabled = page === 1;
            get('historyNext').disabled = page * 50 >= result.total;
        } catch (error) {
            if (error.name !== 'AbortError') { get('historyRows').replaceChildren(); get('historyStatus').textContent = '检索失败，请确认 Deepsee 服务正常后重试。'; }
        }
    }
    function open() {
        if (!dialog) {
            dialog = node('dialog'); dialog.id = 'wechatHistoryDialog';
            dialog.setAttribute('aria-label', '微信历史检索');
            dialog.style.cssText = 'width:min(1200px,96vw);max-height:92vh;border:1px solid var(--border-color,#ddd);border-radius:12px;padding:20px;background:var(--surface-elevated,#fff);color:var(--text-primary,#222)';
            dialog.innerHTML = `<style>
                #wechatHistoryDialog td,#wechatHistoryDialog th{padding:8px;text-align:left;vertical-align:top;border-color:var(--border-color,#ddd);font-size:12px!important;line-height:1.5;height:auto!important;max-height:none!important;white-space:normal;overflow-wrap:anywhere}
                #wechatHistoryDialog th{top:0;z-index:1}
                #wechatHistoryDialog summary{cursor:pointer;white-space:pre-wrap}
                #wechatHistoryDialog details:not([open]) summary{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}
                #wechatHistoryDialog details:not([open]) pre{display:none}
                #wechatHistoryDialog a{color:var(--link,#3b82f6)}
                #wechatHistoryDialog input,#wechatHistoryDialog select{background:var(--surface-elevated,#fff);color:var(--text-primary,#222);border:1px solid var(--border-color,#ddd);padding:4px;border-radius:5px}
                #wechatHistoryDialog::backdrop{background:rgba(0,0,0,.35)}
                </style>
                <header style="display:flex;justify-content:space-between;align-items:center"><h3>微信历史检索</h3><button id="historyClose" class="pagination-btn" type="button">关闭</button></header>
                <p style="font-size:12px;color:var(--text-muted,#666)">检索全部已入库记录，包含收发消息。仅查询本地数据，不触发同步或 AI；附件能否打开取决于本地是否留存。</p>
                <form id="historyForm" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                    <input id="historyQuery" class="filter-input" aria-label="历史关键词" placeholder="内容、备注名或群名" maxlength="200">
                    <label>从 <input id="historyFrom" type="date" aria-label="开始日期"></label>
                    <label>至 <input id="historyTo" type="date" aria-label="结束日期"></label>
                    <select id="historyType" aria-label="历史消息类型"><option value="">全部聊天（不含系统）</option>${Object.entries(types).map(([v,t])=>`<option value="${v}">${t}</option>`).join('')}</select>
                    <select id="historyDirection" aria-label="收发方向"><option value="">收发全部</option><option value="in">收到</option><option value="out">发出</option></select>
                    <button class="pagination-btn" type="submit">检索</button>
                </form>
                <div style="display:flex;gap:12px;align-items:center;margin:12px 0"><span id="historyStatus" role="status"></span><button id="historyPrev" class="pagination-btn">上一页</button><button id="historyNext" class="pagination-btn">下一页</button></div>
                <div id="historyPreview" aria-live="polite"></div>
                <div style="overflow:auto;max-height:58vh"><table style="width:100%;min-width:760px;border-collapse:collapse"><colgroup><col style="width:140px"><col style="width:120px"><col style="width:150px"><col style="width:90px"><col></colgroup><thead><tr><th>时间</th><th>发送人</th><th>聊天对象</th><th>类型</th><th>消息</th></tr></thead><tbody id="historyRows"></tbody></table></div>`;
            document.body.append(dialog);
            get('historyClose').onclick = () => dialog.close();
            dialog.addEventListener('close', () => { controller?.abort(); clearPreview(); });
            get('historyForm').onsubmit = event => { event.preventDefault(); clearPreview(); search(1); };
            get('historyPrev').onclick = () => search(page - 1);
            get('historyNext').onclick = () => search(page + 1);
            const now = new Date(), start = new Date(); start.setMonth(start.getMonth() - 6);
            get('historyFrom').value = dateString(start); get('historyTo').value = dateString(now);
        }
        dialog.showModal();
        get('historyQuery').focus();
        if (!lastQuery) search(1);
    }
    document.getElementById('openWechatHistory')?.addEventListener('click', open);
})();
