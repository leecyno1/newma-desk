(function(){
    const host=document.getElementById('wechatMemorySettings');if(!host)return;
    host.innerHTML=`<h4>阶段性对话记忆</h4><p class="execution-note">回复前读取本地同一会话的双方记录，以“历史聊天记录”交给模型或 Agent。默认最近 50 条、30 天，按预算截取；不会删除聊天记录。群聊默认只纳入同一发送人与对应机器人回复，不跨会话拼接。</p><div class="execution-grid">
    <label>上下文记忆<select id="memoryEnabled"><option value="true">启用</option><option value="false">关闭</option></select></label>
    <label>最近消息数<select id="memoryCount"><option>30</option><option>50</option><option>100</option></select></label>
    <label>Token 预算（估算）<input id="memoryTokens" type="number" min="256" max="16000"></label>
    <label>回看范围（小时）<input id="memoryAge" type="number" min="1" max="4320"><small>720 = 30 天；最高 4320 = 180 天</small></label>
    <label>群聊范围<select id="memoryGroup"><option value="true">同一发送人（推荐）</option><option value="false">本群所有成员</option></select></label></div>
    <div class="execution-actions"><button id="memorySave" class="robot-primary" disabled>保存记忆设置</button><span id="memoryStatus" role="status"></span></div>
    <hr><h4>记忆检查</h4><p class="robot-field-tip">使用已保存配置，只读本地记录，不调用 AI、不发送微信。可核对实际覆盖范围和双方发言。</p>
    <label class="robot-field">联系人 / 群聊<input id="memoryResetChat" list="memoryChatOptions" placeholder="加载联系人后按名称选择，或输入聊天 ID"></label><datalist id="memoryChatOptions"></datalist>
    <label class="robot-field">群聊发送者 ID<input id="memorySender" placeholder="私聊无需填写；群聊按发送人隔离时必填"></label>
    <div class="execution-actions"><button id="memoryContacts">加载联系人</button><button id="memoryInspect">检查上下文</button></div>
    <p id="memoryInspectionStatus" class="robot-inline-hint" role="status"></p><div id="memoryPreview" style="max-height:280px;overflow:auto"></div>
    <details><summary>重新开始此会话</summary><p class="robot-field-tip">仅让后续回复从新阶段开始，不删除原始聊天记录。</p><button id="memoryReset">重置所选聊天记忆</button></details>`;
    const el=id=>document.getElementById(id),status=t=>{el('memoryStatus').textContent=t;};
    async function request(path,method,data){const r=await fetch('/api/wechat-gateway/memory/'+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'设置无效');return d;}
    request('config','GET').then(d=>{el('memoryEnabled').value=String(d.enabled);if(![30,50,100].includes(d.max_messages))el('memoryCount').add(new Option(d.max_messages,d.max_messages));el('memoryCount').value=d.max_messages;el('memoryTokens').value=d.max_tokens;el('memoryAge').value=d.max_age_hours;el('memoryGroup').value=String(d.group_sender_only);el('memorySave').disabled=false;}).catch(e=>status(e.message));
    el('memorySave').onclick=async()=>{try{await request('config','PUT',{enabled:el('memoryEnabled').value==='true',max_messages:Number(el('memoryCount').value),max_tokens:Number(el('memoryTokens').value),max_age_hours:Number(el('memoryAge').value),group_sender_only:el('memoryGroup').value==='true'});status('已保存，后续回复生效');}catch(e){status(e.message);}};
    el('memoryReset').onclick=async()=>{const chat_id=el('memoryResetChat').value.trim();if(!chat_id||!confirm('仅清空此聊天的上下文窗口，不删除原始记录，继续？'))return;try{await request('reset','POST',{chat_id});status('已重置，下一条消息开始新阶段');}catch(e){status(e.message);}};
    el('memoryContacts').onclick=async()=>{
        const button=el('memoryContacts');button.disabled=true;
        try{
            const results=await Promise.all(['/api/contacts?include_labels=0','/api/chats'].map(async url=>{const r=await fetch(url);if(!r.ok)throw Error('联系人读取失败');return r.json();}));
            const options=new Map();
            for(const item of results.flat())if(item.id)options.set(item.id,item.remark_name||item.alias||item.remark||item.name||item.title||item.id);
            el('memoryChatOptions').replaceChildren(...[...options].map(([id,name])=>new Option(name,id)));
            el('memoryInspectionStatus').textContent='已加载，可按备注名称选择联系人。';
        }catch(e){el('memoryInspectionStatus').textContent=e.message;}finally{button.disabled=false;}
    };
    el('memoryInspect').onclick=async()=>{
        const chat_id=el('memoryResetChat').value.trim(),sender_id=el('memorySender').value.trim();
        const output=el('memoryInspectionStatus');
        if(!chat_id){output.textContent='请先选择会话或输入聊天 ID。';return;}
        if(chat_id.endsWith('@chatroom')&&!sender_id&&el('memoryGroup').value==='true'){output.textContent='请填写群聊发送者 ID，避免混用其他成员的记录。';return;}
        const button=el('memoryInspect');button.disabled=true;el('memoryPreview').replaceChildren();
        try{
            const d=await request('inspect?'+new URLSearchParams({chat_id,sender_id}),'GET');const m=d.memory;
            output.textContent=!m.enabled?'对话记忆已关闭。':m.messages?`已纳入 ${m.messages} 条 · 对方 ${m.inbound} / 我方 ${m.outbound} · 约 ${m.estimated_tokens} tokens · ${m.oldest_at.replace('T',' ')} 至 ${m.newest_at.replace('T',' ')}${m.truncated?' · 已按预算截取':''}`:`当前窗口没有记录（回看 ${m.max_age_hours} 小时${m.reset_applied?'，已应用重置边界':''}）。请核对聊天 ID、群聊发送者或历史同步情况。`;
            for(const turn of d.history){const row=document.createElement('p');row.className='robot-field-tip';row.style.whiteSpace='pre-wrap';row.textContent=(turn.timestamp||'').replace('T',' ')+' · '+turn.speaker+'：'+turn.text;el('memoryPreview').append(row);}
        }catch(e){output.textContent=e.message;}finally{button.disabled=false;}
    };
})();
