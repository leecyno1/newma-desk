(function () {
    const host = document.getElementById('clientRecorder');
    if (!host) return;
    host.innerHTML = `<strong>当前设备录音</strong>
        <select id="clientMic" aria-label="录音麦克风"><option value="">默认麦克风</option></select>
        <button class="pagination-btn" id="clientRecordStart">开始录音</button>
        <button class="pagination-btn" id="clientRecordPause" hidden>暂停</button>
        <button class="pagination-btn" id="clientRecordStop" hidden>结束录音</button>
        <button class="pagination-btn" id="clientRecordUpload" hidden>保存并转写</button>
        <label class="pagination-btn">导入音频<input id="clientAudioFile" type="file" accept="audio/*,.webm,.mp4" hidden></label>
        <a id="clientRecordDownload" class="pagination-btn" hidden>下载录音备份</a>
        <button class="pagination-btn" id="clientRecordRetry" hidden>重试处理</button>
        <span role="status" id="clientRecordStatus">当前设备采集，服务电脑本地转写；纪要使用 AI 通道。停止后可试听、下载备份。</span>
        <audio id="clientRecordPreview" controls hidden></audio>`;
    const el = id => document.getElementById(id);
    const say = text => {el('clientRecordStatus').textContent=text;};
    let recorder=null, stream=null, chunks=[], blob=null, url='', timer=null, pollTimer=null, filename='', active=false, started=0;
    let extension='webm';
    const statuses={queued:'已保存，等待本地转写',transcribing:'本地语音转写中',summarizing:'转写完成，正在生成纪要',done:'录音、转写和纪要已完成',needs_setup:'录音已保存，转写环境未就绪',transcription_failed:'转写失败',summary_failed:'转写已完成，纪要生成失败',no_speech:'未检测到有效语音'};
    function buttons(recording) {
        el('clientRecordStart').disabled=recording;
        el('clientAudioFile').disabled=recording;
        el('clientMic').disabled=recording;
        el('clientRecordPause').hidden=!recording;
        el('clientRecordStop').hidden=!recording;
    }
    function release() {stream?.getTracks().forEach(t=>t.stop());stream=null;clearInterval(timer);}
    function preview(value) {
        blob=value;
        if(url) URL.revokeObjectURL(url);
        url=URL.createObjectURL(blob);
        el('clientRecordPreview').src=url; el('clientRecordPreview').hidden=false;
        el('clientRecordDownload').href=url; el('clientRecordDownload').download=`会议录音.${extension}`;
        el('clientRecordDownload').hidden=false; el('clientRecordUpload').hidden=false;
        say(`录音待保存 · ${(blob.size/1024/1024).toFixed(1)} MB。先试听确认；关闭页面前请保存或下载备份。`);
    }
    el('clientRecordStart').onclick=async()=>{
        if(blob && !confirm('当前录音尚在页面中，请先保存或下载备份。确定开始新录音？')) return;
        if(!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
            say('麦克风需要 HTTPS 或本机 localhost。手机通过普通内网 HTTP 访问时，请改用 HTTPS，或用系统录音后导入音频。');return;
        }
        if(!window.MediaRecorder){say('当前浏览器不支持网页录音，请使用系统录音后导入音频。');return;}
        try {
            el('clientRecordStart').disabled=true;
            el('clientAudioFile').disabled=true;
            stream=await navigator.mediaDevices.getUserMedia({audio:el('clientMic').value ? {deviceId:{exact:el('clientMic').value}} : true});
            const selected=el('clientMic').value;
            const devices=await navigator.mediaDevices.enumerateDevices();
            el('clientMic').replaceChildren(new Option('默认麦克风',''),...devices.filter(d=>d.kind==='audioinput').map((d,i)=>new Option(d.label||`麦克风 ${i+1}`,d.deviceId)));
            el('clientMic').value=selected;
            const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));
            recorder=new MediaRecorder(stream,mime?{mimeType:mime}:{});
            extension=recorder.mimeType.includes('mp4')?'m4a':recorder.mimeType.includes('ogg')?'ogg':'webm';
            chunks=[];let size=0;active=true;buttons(true);el('clientRecordUpload').hidden=true;
            el('clientRecordPause').textContent='暂停';
            recorder.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);size+=e.data.size;if(size>120*1024*1024 && recorder.state!=='inactive')recorder.stop();}};
            recorder.onerror=()=>{active=false;say('录音设备出错，请重新连接麦克风。');release();buttons(false);};
            recorder.onstop=()=>{active=false;release();buttons(false);preview(new Blob(chunks,{type:recorder.mimeType}));};
            recorder.start(1000);started=Date.now();
            say('录音中 00:00 · 请保持页面前台，不要锁屏');
            timer=setInterval(()=>{const s=Math.floor((Date.now()-started)/1000);say(`${recorder.state==='paused'?'已暂停':'录音中'} ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} · 保持页面前台，不要锁屏`);},1000);
        }catch(e){active=false;release();buttons(false);say(e.name==='NotAllowedError'?'麦克风权限未获允许，请在浏览器设置中授权；若宿主限制录音，请独立打开会议页。':`无法启动录音：${e.message}`);}
    };
    el('clientRecordPause').onclick=()=>{if(recorder.state==='recording'){recorder.pause();el('clientRecordPause').textContent='继续';}else{recorder.resume();el('clientRecordPause').textContent='暂停';}};
    el('clientRecordStop').onclick=()=>{if(recorder && recorder.state!=='inactive')recorder.stop();};
    el('clientAudioFile').onchange=e=>{const f=e.target.files[0];if(!f)return;if(active){say('请先结束当前录音。');return;}extension=f.name.split('.').pop().toLowerCase();preview(f);};
    async function poll() {
        try{
            const response=await fetch(`/api/recorder/capture/${encodeURIComponent(filename)}`);
            const data=await response.json();if(!response.ok)throw Error(data.detail||'读取进度失败');
            say(`${statuses[data.status]||data.status}。${data.error||''}`);
            if(['queued','transcribing','summarizing'].includes(data.status)){pollTimer=setTimeout(poll,3000);return;}
            el('clientRecordRetry').hidden=data.status==='done'||data.status==='no_speech';
            try{if(typeof loadMinutes==='function')await loadMinutes(false);}catch(_){}
        }catch(e){say(`进度读取失败：${e.message}。录音已保存，可在会议列表查看。`);}
    }
    el('clientRecordUpload').onclick=async()=>{
        if(!blob)return;if(blob.size>128*1024*1024){say('文件超过 128 MB，请先下载备份并分段上传。');return;}
        const form=new FormData();form.append('file',blob,`会议录音.${extension}`);
        el('clientRecordUpload').disabled=true;say('正在保存录音到 Deepsee…');
        try{
            const response=await fetch('/api/recorder/capture',{method:'POST',body:form});
            const data=await response.json();if(!response.ok)throw Error(data.detail||'上传失败');
            filename=data.filename;clearTimeout(pollTimer);el('clientRecordUpload').hidden=true;blob=null;
            await poll();
        }catch(e){say(`保存失败：${e.message}。录音仍可试听和下载，请重试。`);}finally{el('clientRecordUpload').disabled=false;}
    };
    el('clientRecordRetry').onclick=async()=>{
        el('clientRecordRetry').disabled=true;
        try{const r=await fetch(`/api/recorder/capture/${encodeURIComponent(filename)}/retry`,{method:'POST'});if(!r.ok)throw Error((await r.json()).detail||'重试失败');await poll();}
        catch(e){say(e.message);}finally{el('clientRecordRetry').disabled=false;}
    };
    window.addEventListener('beforeunload',e=>{if(active||blob){e.preventDefault();e.returnValue='';}});
})();
