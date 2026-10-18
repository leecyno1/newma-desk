(function () {
    'use strict';
    const root = document.getElementById('aiExecutionSettings');
    if (!root) return;
    const lanes = [['Advanced','高级处理','综合分析、研判、一页通','advanced'], ['Light','轻量处理','消息摘要、分类、纪要、微信回复','light']];
    root.innerHTML = `
      <div class="execution-heading"><div><strong>模型及 Agent 配置</strong><p>选择执行方式，再配置模型。提示词与记忆由 Deepsee 统一提供。</p></div><button id="execDetect">检测本机 Agent</button></div>
      <div id="execInventory" class="execution-inventory" aria-live="polite">正在检测…</div>
      <div class="execution-grid">
        <label>默认执行方式<select id="execMode"><option value="models">内置模型调用（API / 本地服务）</option><option value="agent">外接 Agent</option></select></label>
        <label>外接 Agent<div class="execution-provider"><select id="execProvider"><option value="codex">Codex CLI</option><option value="hermes">Hermes CLI</option><option value="qoder">Qoder CLI</option><option value="claude">Claude CLI</option><option value="http">通用 Agent API</option></select><button id="execCatalog" type="button">探测模型</button></div></label>
      </div>
      <p id="execCatalogStatus" class="execution-note" role="status">检测后可选择模型，也可输入自定义模型 ID。</p>
      <div class="execution-lanes">${lanes.map(([id,title,desc])=>`<div class="execution-lane"><div><strong>${title}</strong><small>${desc}</small></div><label>执行方式<select id="exec${id}"><option value="inherit">跟随默认</option><option value="models">内置模型</option><option value="agent">外接 Agent</option></select></label><div data-agent-model="${id}"><label for="exec${id}Picker">Agent 子模型</label><select id="exec${id}Picker" aria-label="${title} Agent 子模型"><option value="">使用 Agent 默认模型</option><option value="__custom">自定义模型 ID…</option></select><input id="exec${id}Model" aria-label="${title}自定义模型 ID" placeholder="输入自定义模型 ID" hidden><small id="exec${id}Hint"></small></div><button id="execTest${id}">测试</button></div>`).join('')}</div>
      <p id="execEffective" class="execution-note"></p>
      <p id="execConnectionNote" class="execution-note"></p>
      <p id="execMigrationNote" class="execution-note" role="status" hidden></p>
      <details id="execAgentOptions"><summary>运行选项</summary><div class="execution-grid">
        <label data-http>Agent API Base<input id="execUrl" type="url" placeholder="https://服务地址/v1"></label>
        <label data-http>API Key<input id="execKey" type="password" autocomplete="new-password" placeholder="留空保留已保存密钥"></label>
        <label>超时（秒）<input id="execTimeout" type="number" min="10" max="600" value="180"></label>
        <label>失败处理<select id="execFallback"><option value="false">明确报错，不切换</option><option value="true">回退到内置模型</option></select></label>
      </div></details>
      <div class="execution-actions"><button id="execSave" class="primary">保存执行方案</button><span id="aiExecutionStatus" role="status"></span></div>
      <p class="execution-note">内置模型的名称、URL、Key 和权重在下方配置。权重只用于内置模型路由，不控制 Agent。此页控制 Deepsee 后台处理，Newma 聊天设置独立。检测在服务电脑执行；生图和转写仍使用专用接口。</p>`;
    const el = id => document.getElementById(id);
    const status = text => { el('aiExecutionStatus').textContent = text; };
    let dirty = false;
    let catalogModels = [], catalogRequest = 0;
    const fields = {mode:'execMode',provider:'execProvider',advanced_backend:'execAdvanced',light_backend:'execLight',advanced_model:'execAdvancedModel',light_model:'execLightModel',api_url:'execUrl',timeout_seconds:'execTimeout',fallback_to_models:'execFallback'};
    async function json(url, options) {
        const r = await fetch(url, options), d = await r.json();
        if (!r.ok) throw Error(typeof d.detail === 'string' ? d.detail : `请求失败（${r.status}）`);
        return d;
    }
    const post = (url,data) => json(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    function effective(id) {
        const value = el('exec'+id).value;
        if (value !== 'inherit') return value;
        return el('execMode').value;
    }
    function update() {
        const provider = el('execProvider').value;
        root.querySelectorAll('[data-http]').forEach(e=>{e.hidden=provider!=='http';});
        el('execConnectionNote').textContent = provider==='http'
            ? '通用 Agent API 使用兼容 OpenAI Chat Completions 的接口；地址和密钥在运行选项中配置。'
            : '连接与登录沿用服务电脑上 '+provider+' CLI 的配置。这里只选择两档模型，不覆盖服务地址、密钥或协议；提示词与对话记忆仍由 Deepsee 管理。';
        const details = el('builtinModelSettings');
        if (details) details.open=lanes.some(([id])=>effective(id)==='models') || el('execFallback').value==='true';
        lanes.forEach(([id])=>{
            const builtin=effective(id)!=='agent', picker=el('exec'+id+'Picker'), input=el('exec'+id+'Model');
            picker.disabled=builtin; input.disabled=builtin;
            input.hidden=picker.value!=='__custom';
            el('exec'+id+'Hint').textContent=builtin?'使用下方同档内置模型；切换为外接 Agent 后可选子模型。':'此档独立选模型；留空沿用 CLI 默认（Agent API 必填）。';
        });
        el('execEffective').textContent = (dirty?'待保存：':'当前方案：')+lanes.map(([id,title])=>`${title} → ${effective(id)==='agent' ? provider : '内置模型路由'}`).join(' ｜ ');
    }
    function populateModels() {
        lanes.forEach(([id])=>{
            const picker=el('exec'+id+'Picker'), value=el('exec'+id+'Model').value;
            picker.replaceChildren(new Option('使用 Agent 默认模型',''),...catalogModels.map(m=>new Option(m,m)),new Option('自定义模型 ID…','__custom'));
            picker.value=value?(catalogModels.includes(value)?value:'__custom'):'';
        });
        update();
    }
    function changed() { dirty=true; status('有未保存修改'); update(); }
    function fill(d) {
        Object.entries(fields).forEach(([k,id])=>{el(id).value=String(d[k]??(k.endsWith('_backend')?'inherit':''));});
        el('execKey').value='';
        el('execMigrationNote').textContent=d.configuration_notice||'';
        el('execMigrationNote').hidden=!d.configuration_notice;
        dirty=false; populateModels(); status('已保存');
    }
    root.addEventListener('input',changed);
    root.addEventListener('change',changed);
    lanes.forEach(([id])=>{el('exec'+id+'Picker').onchange=()=>{
        const picker=el('exec'+id+'Picker'), input=el('exec'+id+'Model');
        if(picker.value!=='__custom') input.value=picker.value;
        changed(); if(picker.value==='__custom') input.focus();
    };});
    function selectProvider(provider) {
        const previous=el('execProvider').dataset.current;
        el('execProvider').value=provider;
        el('execProvider').dataset.current=provider;
        if(previous!==provider){
            // Credentials and model names belong to the selected Agent, not its neighbour.
            el('execUrl').value=''; el('execKey').value='';
            lanes.forEach(([id])=>{el('exec'+id+'Model').value='';});
        }
        catalogModels=[]; populateModels(); changed(); probeModels();
    }
    el('execProvider').onchange=()=>selectProvider(el('execProvider').value);
    ['execUrl','execKey'].forEach(id=>{el(id).addEventListener('input',()=>{
        ++catalogRequest; catalogModels=[]; populateModels(); el('execCatalog').disabled=false;
        el('execCatalogStatus').textContent='连接信息已修改，请重新探测模型。';
    });});
    el('execMode').addEventListener('change',()=>{lanes.forEach(([id])=>{el('exec'+id).value='inherit';}); changed();});
    el('execSave').onclick=async()=>{
        const data=Object.fromEntries(Object.entries(fields).map(([k,id])=>[k,el(id).value]));
        data.timeout_seconds=Number(data.timeout_seconds); data.fallback_to_models=data.fallback_to_models==='true';
        if(data.provider!=='http'){data.api_url='';data.api_key='';}
        else if(el('execKey').value) data.api_key=el('execKey').value;
        el('execSave').disabled=true;
        try {fill(await json('/api/ai/execution',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}));}
        catch(e){status(e.message);} finally{el('execSave').disabled=false;}
    };
    for(const [id,,,tier] of lanes) el('execTest'+id).onclick=async()=>{
        if(dirty){status('请先保存修改再测试');return;}
        const b=el('execTest'+id);b.disabled=true;status('正在测试，不发送微信消息…');
        try{const d=await post('/api/ai/execution/test',{tier});status(d.ok?`成功 · ${d.execution?.provider||'内置模型'} · ${d.execution?.final_model||''} · ${d.elapsed_seconds}s`:d.error);}
        catch(e){status(e.message);}finally{b.disabled=false;}
    };
    async function detect(){
        el('execDetect').disabled=true;
        try{
            const d=await json('/api/ai/agents'); el('execInventory').replaceChildren();
            for(const a of d.items){
                const b=document.createElement('button');b.type='button';b.className='execution-agent';b.disabled=!a.installed;
                b.textContent=`${a.provider} · ${!a.installed?'未安装':a.status==='version_unavailable'?'已安装 · 版本未验证':'已安装'}${a.version?' · '+a.version:''}`;
                b.title='点击选用。安装不代表授权可用，保存后请测试';
                b.onclick=()=>selectProvider(a.provider);
                el('execInventory').append(b);
            }
        }catch(e){el('execInventory').textContent=e.message;}finally{el('execDetect').disabled=false;}
    }
    el('execDetect').onclick=async()=>{await detect();await probeModels();};
    async function probeModels(){
        const request=++catalogRequest, provider=el('execProvider').value;
        const b=el('execCatalog');b.disabled=true;el('execCatalogStatus').textContent='正在探测 '+provider+' 模型…';
        try{const remote=provider==='http';
            const d=await post('/api/ai/models/catalog',{source:'agent',provider,api_url:remote?el('execUrl').value:'',api_key:remote?el('execKey').value:''});
            if(request!==catalogRequest)return;
            catalogModels=d.models;populateModels();
            el('execCatalogStatus').textContent=`找到 ${d.models.length} 个模型。${d.note||''}`;
        }catch(e){if(request===catalogRequest){catalogModels=[];populateModels();el('execCatalogStatus').textContent=e.message+'；可继续自定义模型 ID。';}}
        finally{if(request===catalogRequest)b.disabled=false;}
    }
    el('execCatalog').onclick=probeModels;
    window.discoverChannelModels=async(button,lane)=>{
        const row=button.closest('tr'), field=k=>row.querySelector(`[data-k="${k}"]`), key=field('api_key');
        button.disabled=true;const label=button.textContent;button.textContent='读取中…';
        try{
            const d=await post('/api/ai/models/catalog',{lane,channel_id:field('id').value,api_url:field('api_url').value,api_key:key.dataset.secretMasked==='1'?'':key.value});
            let select=row.querySelector('.model-catalog-picker');if(!select){select=document.createElement('select');select.className='model-catalog-picker';field('model').after(select);}
            select.replaceChildren(new Option('选择模型（'+d.models.length+'）',''),...d.models.map(m=>new Option(m,m)));
            select.onchange=()=>{if(select.value){field('model').value=select.value;field('model').dispatchEvent(new Event('input',{bubbles:true}));}};select.focus();
        }catch(e){alert(e.message);}finally{button.disabled=false;button.textContent=label;}
    };
    json('/api/ai/execution').then(d=>{fill(d);el('execProvider').dataset.current=d.provider;return probeModels();}).catch(e=>status(e.message));detect();
})();
