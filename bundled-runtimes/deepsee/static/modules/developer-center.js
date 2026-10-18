(() => {
    const root = document.getElementById('deepsee-developer');
    if (!root) return;
    const labels = {'messages:read':'微信消息', 'contacts:read':'联系人 / 标签', 'chats:read':'会话',
        'emails:read':'邮件', 'news:read':'新闻', 'media:read':'自媒体', 'mp:read':'公众号',
        'meetings:read':'会议', 'scores:read':'评分证据', 'attachments:read':'本地附件'};
    let projects = [], editing = null, loading = false;
    root.innerHTML = `
        <header class="dev-head"><div class="dev-kicker">DEEPSEE / DATA ACCESS</div>
        <h3>开发者中心</h3><p>让你的项目读取 Deepsee 已收集的数据。独立密钥，按需授权，随时停用。</p>
        <code id="dev-base"></code></header><div id="dev-status" class="dev-status" role="status"></div>
        <div class="dev-layout"><div><form id="dev-form" class="dev-box">
        <h4 id="dev-form-title">创建接入项目</h4>
        <label class="dev-field">项目名称<input id="dev-name" required maxlength="80" placeholder="例如：研究助手"></label>
        <label class="dev-field">每分钟请求上限<input id="dev-rpm" type="number" min="1" max="10000" value="120" required></label>
        <div id="dev-scopes" class="dev-scopes"></div>
        <p>权限覆盖本实例对应类别的全部数据，暂不支持按群聊隔离。附件还需勾选微信消息。</p>
        <div class="dev-actions"><button class="dev-primary" type="submit">保存项目</button><button id="dev-cancel" type="button">重置</button></div>
        </form><section class="dev-box"><h4>接入约定</h4><p>使用 Bearer 密钥调用只读 API。CLI 通过环境变量读取密钥，不直接访问数据库。</p>
        <code>DEEPSEE_API_KEY<br>DEEPSEE_API_BASE<br>python scripts/deepsee.py search "关键词"</code>
        <p>只管理本机项目。跨设备调用请先配置 HTTPS 与访问控制；不要代理开放开发者管理接口。</p>
        <p>新闻等内容仅覆盖本地留存；附件未留存时返回 404。评分无已验证样本时返回空值。</p></section></div>
        <section class="dev-box"><h4>接入项目 <button id="dev-refresh" type="button">刷新</button></h4><div id="dev-projects">尚未加载</div></section></div>
        <section class="dev-box"><h4>最近调用</h4><p>记录项目、接口、状态与时间，保留 30 天；不记录查询词、消息正文或密钥。</p>
        <div id="dev-logs" class="dev-log"></div></section>
        <dialog id="dev-key-dialog"><h4>请立即保存密钥</h4><p>完整密钥仅显示这一次。不要写进前端代码或提交到代码仓库。</p>
        <textarea id="dev-key" aria-label="新项目密钥" readonly spellcheck="false"></textarea><div class="dev-actions">
        <button id="dev-copy" type="button">复制密钥</button><button id="dev-close" type="button" class="dev-primary">已保存，关闭</button></div></dialog>`;
    const $ = id => root.querySelector(`#${id}`);
    $('dev-base').textContent = `${location.origin}/api/v1`;
    for (const [scope, label] of Object.entries(labels)) {
        const node = document.createElement('label');
        const input = document.createElement('input'); input.type = 'checkbox'; input.value = scope;
        node.append(input, document.createTextNode(label)); $('dev-scopes').append(node);
    }
    const status = text => { $('dev-status').textContent = text; };
    async function request(path, method = 'GET', body) {
        const response = await fetch(`/api/developer/${path}`, {method, cache:'no-store',
            headers:{'X-Deepsee-Admin':'1', ...(body ? {'Content-Type':'application/json'} : {})},
            body: body ? JSON.stringify(body) : undefined});
        if (!response.ok) {
            if (response.status === 403) throw new Error('开发者中心仅支持本机同源访问，请在本机打开 http://127.0.0.1:8001/。');
            throw new Error(`操作失败（${response.status}），请检查权限、项目参数与服务状态。`);
        }
        return response.status === 204 ? null : response.json();
    }
    function reset() {
        editing = null; $('dev-form').reset(); $('dev-form-title').textContent = '创建接入项目';
    }
    function showKey(token) {
        $('dev-key').value = token; $('dev-key-dialog').showModal();
    }
    function button(text, fn) {
        const el = document.createElement('button'); el.type = 'button'; el.textContent = text;
        el.onclick = async () => {
            el.disabled = true;
            try { await fn(); } catch (error) { status(error.message); } finally { el.disabled = false; }
        }; return el;
    }
    function renderProjects() {
        const container = $('dev-projects'); container.replaceChildren();
        if (!projects.length) { container.textContent = '还没有接入项目。先选择需要读取的数据，再创建密钥。'; return; }
        for (const project of projects) {
            const card = document.createElement('div'); card.className = 'dev-project';
            const title = document.createElement('strong'); title.textContent = `${project.name} · ${project.enabled ? '已启用' : '已停用'}`;
            const info = document.createElement('small'); info.textContent = `${project.requests_per_minute} 次/分钟 · ${project.scopes.map(x => labels[x] || x).join('、')}`;
            const identity = document.createElement('small'); identity.textContent = project.source === 'environment' ? '由环境配置管理' : `密钥前缀 ${project.token_prefix}…`;
            card.append(title, info, identity);
            if (project.source === 'managed') {
                const actions = document.createElement('div'); actions.className = 'dev-actions';
                actions.append(button('编辑权限', () => {
                    editing = project; $('dev-form-title').textContent = '编辑项目'; $('dev-name').value = project.name;
                    $('dev-rpm').value = project.requests_per_minute;
                    $('dev-scopes').querySelectorAll('input').forEach(el => { el.checked = project.scopes.includes(el.value); });
                    $('dev-name').focus();
                }), button('轮换密钥', async () => {
                    if (!window.confirm(`轮换 ${project.name} 的密钥？旧密钥将立即失效。`)) return;
                    const result = await request(`projects/${project.id}/rotate`, 'POST'); showKey(result.token); await load();
                }), button(project.enabled ? '停用' : '启用', async () => {
                    if (!window.confirm(`${project.enabled ? '停用' : '启用'} ${project.name}？`)) return;
                    await request(`projects/${project.id}`, project.enabled ? 'DELETE' : 'PUT', project.enabled ? undefined : {
                        name:project.name, scopes:project.scopes, requests_per_minute:project.requests_per_minute, enabled:true});
                    reset(); await load();
                })); card.append(actions);
            }
            container.append(card);
        }
    }
    function renderLogs(rows) {
        const container = $('dev-logs'); container.replaceChildren();
        if (!rows.length) { container.textContent = '暂无已认证项目的调用记录。'; return; }
        const table = document.createElement('table'); const head = document.createElement('tr');
        for (const label of ['时间', '项目', '接口', '状态', '请求编号']) { const th = document.createElement('th'); th.textContent = label; head.append(th); }
        table.append(head);
        for (const row of rows) {
            const tr = document.createElement('tr');
            for (const value of [new Date(row.at).toLocaleString(), projects.find(p => p.id === row.project_id)?.name || row.project_id, row.route, row.status, row.request_id]) {
                const td = document.createElement('td'); td.textContent = String(value); tr.append(td);
            } table.append(tr);
        } container.append(table);
    }
    async function load() {
        if (loading) return; loading = true;
        try {
            const [result, logs] = await Promise.all([request('projects'), request('requests')]);
            projects = result.data; renderProjects(); renderLogs(logs.data); status('只读 API · 本机管理 · 不开放匿名访问');
        } catch (error) { status(error.message); } finally { loading = false; }
    }
    $('dev-form').onsubmit = async event => {
        event.preventDefault(); const submit = $('dev-form').querySelector('[type=submit]'); submit.disabled = true;
        try {
            const scopes = [...$('dev-scopes').querySelectorAll('input:checked')].map(el => el.value);
            if (!scopes.length) throw new Error('请至少选择一类可读取的数据。');
            if (scopes.includes('attachments:read') && !scopes.includes('messages:read')) throw new Error('读取附件还需要微信消息权限。');
            const body = {name:$('dev-name').value.trim(), requests_per_minute:Number($('dev-rpm').value), scopes};
            if (editing) body.enabled = editing.enabled;
            const result = await request(editing ? `projects/${editing.id}` : 'projects', editing ? 'PUT' : 'POST', body);
            if (result.token) showKey(result.token);
            reset(); await load();
        } catch (error) { status(error.message); } finally { submit.disabled = false; }
    };
    $('dev-cancel').onclick = reset; $('dev-refresh').onclick = load;
    $('dev-close').onclick = () => $('dev-key-dialog').close();
    $('dev-key-dialog').addEventListener('close', () => { $('dev-key').value = ''; $('dev-copy').textContent = '复制密钥'; });
    $('dev-copy').onclick = async () => {
        try { await navigator.clipboard.writeText($('dev-key').value); $('dev-copy').textContent = '已复制'; }
        catch { $('dev-key').select(); $('dev-copy').textContent = '请手动复制选中密钥'; }
    };
    window.DeepseeDeveloper = {load};
})();
