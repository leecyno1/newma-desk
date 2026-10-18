(function(){
    const host=document.getElementById('socialSourcesSettings');if(!host)return;
    host.innerHTML=`<details><summary>扩展采集渠道 · RSS / 社区 / Agent Reach</summary><p class="execution-note">公开订阅无需登录；社交渠道通过 Agent Reach 检测本机 OpenCLI，使用已有浏览器登录。只读采集，不绕过验证码。Instagram 填作者用户名，其他平台填搜索词，RSS 填订阅地址。</p><div id="socialSourcesRows"></div><div class="execution-actions"><button id="socialSourceAdd">添加渠道</button><button id="socialSourceSave">保存渠道</button><button id="socialSourceHealth">检测渠道</button><button id="socialSourceRun">立即采集</button><span id="socialSourceStatus" role="status"></span></div><div id="socialSourceHealthList" class="execution-note"></div></details>`;
    const el=id=>document.getElementById(id),status=t=>{el('socialSourceStatus').textContent=t;};
    const platforms={rss:'RSS / Atom',v2ex:'V2EX 热门',twitter:'Twitter / X',reddit:'Reddit',bilibili:'B站',xiaohongshu:'小红书',facebook:'Facebook',instagram:'Instagram 作者'};
    let dirty=false;
    async function request(path,method='GET',data){const r=await fetch('/api/collector/'+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const d=await r.json();if(!r.ok)throw Error('请求失败，请检查输入或服务状态');return d;}
    function row(source){
        const line=document.createElement('div');line.className='execution-actions';
        const enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=source.enabled!==false;enabled.setAttribute('aria-label','启用渠道');
        const select=document.createElement('select');Object.entries(platforms).forEach(([k,v])=>select.add(new Option(v,k)));select.value=source.platform;
        const input=document.createElement('input');input.value=source.query||'';input.placeholder='订阅地址 / 搜索词 / 作者';input.style.flex='1';
        const del=document.createElement('button');del.textContent='移除';del.onclick=()=>{line.remove();dirty=true;status('有未保存修改');};
        line.append(enabled,select,input,del);line.addEventListener('input',()=>{dirty=true;status('有未保存修改');});el('socialSourcesRows').append(line);
    }
    request('sources').then(d=>d.sources.forEach(row)).catch(e=>status(e.message));
    el('socialSourceAdd').onclick=()=>{row({platform:'rss'});dirty=true;};
    el('socialSourceSave').onclick=async()=>{try{const sources=Array.from(el('socialSourcesRows').children).map(r=>({enabled:r.children[0].checked,platform:r.children[1].value,query:r.children[2].value}));await request('sources','PUT',{sources});dirty=false;status('已保存');}catch(e){status(e.message);}};
    el('socialSourceHealth').onclick=async()=>{const b=el('socialSourceHealth');b.disabled=true;status('检测本机采集后端…');try{const d=await request('sources/health');el('socialSourceHealthList').textContent=Object.values(d.channels||{}).map(c=>`${c.name}：${c.status==='ok'?'后端就绪':'需配置'}${c.backend?' · '+c.backend:''}`).join(' ｜ ')||d.message;status('检测完成；实际采集仍受登录和限流影响');}catch(e){status(e.message);}finally{b.disabled=false;}};
    el('socialSourceRun').onclick=async()=>{if(dirty){status('请先保存渠道');return;}const b=el('socialSourceRun');b.disabled=true;status('采集中，请稍候…');try{const d=await request('sources/refresh','POST');status(`采集 ${d.count} 条；`+d.results.map(r=>`${platforms[r.platform]||r.platform} ${r.ok?r.count+' 条':r.error}`).join(' / '));if(typeof loadFoloItems==='function')await loadFoloItems();else if(typeof ensureFoloModuleLoaded==='function')await ensureFoloModuleLoaded(true);}catch(e){status(e.message);}finally{b.disabled=false;}};
})();
