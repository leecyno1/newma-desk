/* Policy scopes never share drafts or save payloads. */
(() => {
    const $=id=>document.getElementById(id);
    const lines=id=>[...new Set(String($(id)?.value||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean))];
    const checked=id=>!!$(id)?.checked;
    const fields={
        reply:[['whitelist_chat_ids','wechatTriggerWhitelistChatIds','会话白名单'],['blacklist_chat_ids','wechatTriggerBlacklistChatIds','会话黑名单'],['whitelist_sender_ids','wechatTriggerWhitelistSenderIds','发送者白名单'],['blacklist_sender_ids','wechatTriggerBlacklistSenderIds','发送者黑名单']],
        data:[['whitelist_talkers','dataWhitelistTalkers','会话白名单'],['blacklist_talkers','dataBlacklistTalkers','会话黑名单'],['whitelist_senders','dataWhitelistSenders','发送者白名单'],['blacklist_senders','dataBlacklistSenders','发送者黑名单']],
    };
    const states={reply:{loaded:false,dirty:false},data:{loaded:false,dirty:false}};
    const titles={reply:'自动回复名单',data:'数据筛选名单'};
    const root=$('policyLists');
    root.innerHTML='<p class="policy-intro">两套名单独立保存，互不复制。先选择要控制的是“机器人回复”还是“数据”。</p><div class="policy-scope-tabs" role="tablist" aria-label="名单作用范围">'+Object.keys(fields).map(scope=>
        '<button type="button" id="policyTab-'+scope+'" role="tab" aria-controls="policyPanel-'+scope+'" aria-selected="'+(scope==='reply')+'" tabindex="'+(scope==='reply'?0:-1)+'" data-scope="'+scope+'"><strong>'+titles[scope]+'</strong><small>'+(scope==='reply'?'谁可以触发机器人':'历史导入与模块展示')+'</small></button>').join('')+'</div>'+
        Object.entries(fields).map(([scope,items])=>'<section id="policyPanel-'+scope+'" class="policy-scope-panel" role="tabpanel" aria-labelledby="policyTab-'+scope+'" '+(scope==='data'?'hidden':'')+'>'+
        '<header class="policy-heading"><div><h4>'+titles[scope]+'</h4><p>'+(scope==='reply'?'仅控制自动回复，不影响历史导入、列表展示或人工群发。':'用于 Chatlog 历史导入及微信、邮件等已接入筛选的模块；不作为机器人触发条件。')+'</p></div><span class="policy-scope-badge">'+(scope==='reply'?'回复范围':'数据范围')+'</span></header>'+
        '<p class="policy-help">'+(scope==='reply'?'会话控制整段私聊或群聊，发送者控制具体成员。开启的两类白名单须同时满足；黑名单优先。兼容旧配置：开启但留空的白名单不限制回复。':'历史导入：任一白名单有内容时，仅导入命中会话或发送者的消息，黑名单优先；不删除已存记录。展示模式只影响当前浏览器，不改变历史导入规则。')+'</p>'+
        '<div class="policy-quick-add"><input id="policyContact-'+scope+'" list="policyContactOptions" aria-label="'+titles[scope]+'联系人或群聊" placeholder="选择联系人 / 群聊，或输入 ID"><select id="policyTarget-'+scope+'" aria-label="加入哪份'+titles[scope]+'">'+items.map(([,id,title])=>'<option value="'+id+'">'+title+'</option>').join('')+'</select><button type="button" data-candidates="'+scope+'">加载联系人</button><button type="button" data-add="'+scope+'">加入草稿</button></div>'+
        '<div class="policy-card-grid">'+items.map(([key,id,title])=>'<div class="policy-list-card" data-tone="'+(key.startsWith('white')?'allow':'block')+'"><div class="policy-card-title"><label for="'+id+'">'+title+'</label><span id="'+id+'Count">0 项</span></div>'+
        (scope==='reply'?'<label class="policy-enable"><input type="checkbox" id="'+id+'Enabled" aria-label="启用自动回复'+title+'">启用此名单</label>':'<small class="policy-enable">名单有内容时参与筛选</small>')+
        '<textarea id="'+id+'" rows="4" aria-label="'+titles[scope]+' · '+title+'" placeholder="'+(title.startsWith('会话')?'私聊 wxid 或群聊 ID':'发送者 ID')+'&#10;每行一个，支持粘贴多行" disabled></textarea></div>').join('')+'</div>'+
        (scope==='reply'?'<div class="policy-extra"><label for="robotBlockedKeywords">不回复的关键词<textarea id="robotBlockedKeywords" rows="2" placeholder="每行一个；命中后不回复"></textarea></label><label for="wechatTriggerMinTextLength">消息最短字数<input id="wechatTriggerMinTextLength" type="number" min="0" max="10000" value="1"><small>去掉触发前缀后计算</small></label></div>':
        '<div class="policy-extra"><label for="filterMode">当前浏览器展示模式<select id="filterMode" onchange="updateFilterMode()"><option value="none">不筛选</option><option value="whitelist">仅白名单</option><option value="blacklist">排除黑名单</option><option value="both">白名单优先（保留现有展示逻辑）</option></select></label><p class="policy-help">实时 WXWS 接收不读取此名单。如需限制设备接收或发送，请到“微信连接 → 连接级收发限制”。</p></div>')+
        '<footer class="policy-footer"><span id="'+scope+'ListStatus" role="status">尚未加载</span><div><button type="button" data-reload="'+scope+'">重载</button><button type="button" data-save="'+scope+'" class="save-btn" disabled>保存'+titles[scope]+'</button></div></footer>'+
        (scope==='data'?'<div class="policy-file-actions"><button type="button" id="policyImport">导入数据名单</button><button type="button" id="policyExport">导出已保存数据名单</button><small>导入只填入草稿，确认后再保存。</small></div>':'')+'</section>').join('')+
        '<datalist id="policyContactOptions"></datalist><p class="policy-footnote">连接级收发限制是两套名单之外的底层限制，仍可能拦截接收和发送。<button type="button" id="policyConnectionLink">查看微信连接 →</button></p>';
    const status=(scope,text)=>{$(scope+'ListStatus').textContent=text;};
    async function request(path,body){
        const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'请求失败');return d;
    }
    function counts(scope){fields[scope].forEach(([,id])=>{$(id+'Count').textContent=lines(id).length+' 项';});}
    function setBusy(scope,busy){
        $('policyPanel-'+scope).querySelectorAll('input,textarea,button').forEach(el=>{el.disabled=busy;});
        root.querySelector('[data-save="'+scope+'"]').disabled=busy||!states[scope].loaded;
    }
    function fill(scope,data){
        fields[scope].forEach(([key,id])=>{$(id).value=(data[key]||[]).join('\n');if(scope==='reply')$(id+'Enabled').checked=!!data[key+'_enabled'];});
        if(scope==='reply'){$('robotBlockedKeywords').value=(data.blocked_keywords||[]).join('\n');$('wechatTriggerMinTextLength').value=data.min_text_length??1;}
        states[scope].loaded=true;states[scope].dirty=false;counts(scope);status(scope,'已加载 · 修改后独立保存');
    }
    async function loadScope(scope,force=false){
        const state=states[scope];if(state.loading)return state.loading;if(state.loaded&&!force)return;
        if(force&&state.dirty&&!confirm('重载将放弃这份名单的未保存修改，继续吗？'))return;
        setBusy(scope,true);status(scope,'加载中…');
        state.loading=(async()=>{try{
            fill(scope,await request(scope==='reply'?'/api/wechat-gateway/trigger-rules':'/api/filters'));
            if(scope==='data')await loadFiltersFromBackend();
        }catch(e){status(scope,'加载失败：'+e.message+'，请重载');}finally{state.loading=null;setBusy(scope,false);}})();
        return state.loading;
    }
    function selectScope(scope,focus=false){
        if(!fields[scope])return;
        for(const key of Object.keys(fields)){$('policyPanel-'+key).hidden=key!==scope;$('policyTab-'+key).setAttribute('aria-selected',String(key===scope));$('policyTab-'+key).tabIndex=key===scope?0:-1;}
        if(focus)$('policyTab-'+scope).focus();loadScope(scope);
    }
    async function saveScope(scope){
        if(!states[scope].loaded)return;
        const invalid=[...$('policyPanel-'+scope).querySelectorAll('input')].find(el=>!el.checkValidity());
        if(invalid){invalid.reportValidity();return;}
        const payload={};
        for(const [key,id] of fields[scope]){payload[key]=lines(id);if(scope==='reply')payload[key+'_enabled']=checked(id+'Enabled');}
        if(scope==='reply'){
            payload.blocked_keywords=lines('robotBlockedKeywords');payload.min_text_length=Number($('wechatTriggerMinTextLength').value);
            if(!confirm('保存后立即影响自动回复范围，不改变总开关。确认名单正确吗？'))return;
        }
        setBusy(scope,true);status(scope,'保存中…');
        try{
            const result=await request(scope==='reply'?'/api/wechat-gateway/trigger-rules':'/api/filters',payload);
            fill(scope,scope==='reply'?result.rules:result);
            if(scope==='data')await loadFiltersFromBackend();
            status(scope,'已保存 · '+titles[scope]+'独立生效');
        }catch(e){status(scope,'保存失败：'+e.message);}finally{setBusy(scope,false);}
    }
    root.addEventListener('input',event=>{
        const panel=event.target.closest('.policy-scope-panel');if(!panel||event.target.id==='filterMode'||event.target.closest('.policy-quick-add'))return;
        const scope=panel.id.replace('policyPanel-','');states[scope].dirty=true;counts(scope);status(scope,'未保存修改 · 仅影响'+titles[scope]);
    });
    root.querySelectorAll('[data-scope]').forEach(b=>{b.onclick=()=>selectScope(b.dataset.scope);});
    root.querySelectorAll('[data-reload]').forEach(b=>{b.onclick=()=>loadScope(b.dataset.reload,true);});
    root.querySelectorAll('[data-save]').forEach(b=>{b.onclick=()=>saveScope(b.dataset.save);});
    root.querySelectorAll('[data-candidates]').forEach(b=>{b.onclick=async()=>{
        b.disabled=true;
        try{
            const [contacts,chats]=await Promise.all([request('/api/contacts?include_labels=0'),request('/api/chats')]);
            const candidates=new Map();
            for(const item of [...contacts,...chats]){
                if(item.id)candidates.set(String(item.id),item.remark_name||item.remark||item.name||item.title||String(item.id));
            }
            $('policyContactOptions').replaceChildren(...[...candidates].map(([id,name])=>new Option(name,id)));
            status(b.dataset.candidates,'联系人已加载，可按名称选择；选择后加入草稿。');
        }catch(e){status(b.dataset.candidates,'联系人加载失败：'+e.message);}finally{b.disabled=false;}
    };});
    root.querySelectorAll('[data-add]').forEach(b=>{b.onclick=()=>{
        const scope=b.dataset.add;if(!states[scope].loaded)return;
        const input=$('policyContact-'+scope),id=$('policyTarget-'+scope).value,value=input.value.trim();
        if(!value){input.focus();return;}
        $(id).value=[...new Set([...lines(id),value])].join('\n');
        states[scope].dirty=true;counts(scope);input.value='';status(scope,'已加入草稿，确认启用状态后保存');
    };});
    root.querySelector('[role=tablist]').onkeydown=event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        event.preventDefault();selectScope(event.key==='Home'?'reply':event.key==='End'?'data':event.target.dataset.scope==='reply'?'data':'reply',true);
    };
    $('policyExport').onclick=()=>exportLists();
    $('policyImport').onclick=()=>{
        const input=document.createElement('input');input.type='file';input.accept='.json,application/json';
        input.onchange=async()=>{try{
            if(!input.files[0])return;
            const data=JSON.parse(await input.files[0].text());
            if(!fields.data.every(([key])=>Array.isArray(data[key])&&data[key].every(x=>typeof x==='string')))throw Error('需要包含四类数据名单的 JSON 文件');
            fill('data',data);states.data.dirty=true;status('data','已导入草稿，确认后保存');
        }catch(e){status('data','导入失败：'+e.message);}};input.click();
    };
    $('policyConnectionLink').onclick=()=>{open('settings-wechat-engine');$('gatewayAccessPolicy').open=true;};
    function open(id,scope){
        openModuleTab('function-settings');initSettingsLayout();
        document.querySelector('.settings-nav-item[data-target="'+id+'"]')?.click();
        if(id==='settings-blackwhite')selectScope(scope||'reply');
    }
    async function save(button,statusId,path,payload){
        button.disabled=true;$(statusId).textContent='保存中…';
        try{await request(path,payload);$(statusId).textContent='已保存';}
        catch(e){$(statusId).textContent=e.message;}finally{button.disabled=false;}
    }
    let accessLoaded=false;
    const accessSave=$('gatewayAccessPolicy').querySelector('.save-btn');
    accessSave.disabled=true;
    $('gatewayAccessPolicy').addEventListener('toggle',async()=>{
        if(!$('gatewayAccessPolicy').open||accessLoaded)return;
        try{
            const config=await request('/api/wechat-gateway/config');
            for(const [key,id] of [['allow_chat_ids','AllowChatIds'],['block_chat_ids','BlockChatIds']]){
                $('wechatGateway'+id).value=(config[key]||[]).join('\n');$('wechatGateway'+id+'Enabled').checked=!!config[key+'_enabled'];
            }
            $('wechatGatewayKeywordBlocklist').value=(config.keyword_blocklist||[]).join('\n');
            for(const [key,id] of [['rate_limit_per_chat_per_minute','RateLimit'],['outbound_random_delay_min_seconds','DelayMin'],['outbound_random_delay_max_seconds','DelayMax']])$('wechatGateway'+id).value=config[key];
            accessLoaded=true;accessSave.disabled=false;$('accessPolicyStatus').textContent='已加载 · 与业务名单分别保存';
        }catch(e){$('accessPolicyStatus').textContent='加载失败，请收起后重试：'+e.message;}
    });
    function saveAccessPolicy(button){
        if(!accessLoaded)return;
        return save(button,'accessPolicyStatus','/api/wechat-gateway/config',{
            allow_chat_ids_enabled:checked('wechatGatewayAllowChatIdsEnabled'),allow_chat_ids:lines('wechatGatewayAllowChatIds'),
            block_chat_ids_enabled:checked('wechatGatewayBlockChatIdsEnabled'),block_chat_ids:lines('wechatGatewayBlockChatIds'),
            keyword_blocklist:lines('wechatGatewayKeywordBlocklist'),rate_limit_per_chat_per_minute:Number($('wechatGatewayRateLimit').value),
            outbound_random_delay_min_seconds:Number($('wechatGatewayDelayMin').value),outbound_random_delay_max_seconds:Number($('wechatGatewayDelayMax').value),
        });
    }
    async function importHistory(button){
        const days=Math.max(1,Math.min(180,Number($('syncDays').value)||7));
        button.disabled=true;$('syncStatus').textContent='正在从 Chatlog 补齐历史，不触发自动回复…';
        try{const d=await request('/api/sync/chatlog/full?days='+days,{});$('syncStatus').textContent='完成 · 新增 '+(d.inserted??d.messages_inserted??0)+' 条';}
        catch(e){$('syncStatus').textContent=String(e.message);}finally{button.disabled=false;}
    }
    function saveSummary(button){return save(button,'wechatSummaryStatus','/api/config/ai-runtime',{enable_msg_tool_overlay:checked('cfgEnableMsgOverlay')});}
    window.DeepseeSettings={open,saveAccessPolicy,importHistory,saveSummary,loadLists:()=>selectScope('reply'),selectScope};
})();
