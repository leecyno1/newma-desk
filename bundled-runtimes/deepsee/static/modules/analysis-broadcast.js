/* Review the script first. Playback always requires an explicit user action. */
(() => {
    let panel, objectURL, utterance, duration = 5, synthesizing = false;
    const $ = id => panel.querySelector('#' + id);
    function stop() {
        window.speechSynthesis?.cancel();
        if (panel) { const audio = $('broadcastAudio'); audio.pause(); audio.currentTime = 0; }
        utterance = null;
    }
    function download(blob, filename) {
        const url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 3000);
    }
    function voices() {
        if (!panel || !window.speechSynthesis) return;
        const select = $('broadcastVoice'), selected = select.value;
        select.replaceChildren(new Option('设备默认声音', ''));
        for (const voice of speechSynthesis.getVoices()) {
            if (/^zh/i.test(voice.lang)) select.add(new Option(voice.name + (voice.localService ? ' · 本机' : ' · 在线'), voice.voiceURI));
        }
        select.value = selected;
    }
    function open(result, anchor) {
        stop();
        if (objectURL) URL.revokeObjectURL(objectURL);
        objectURL = null;
        if (!panel) {
            panel = document.createElement('section');
            panel.className = 'broadcast-player'; panel.setAttribute('aria-label', '分析播报');
            panel.innerHTML = `<div class="broadcast-controls"><strong>分析播报</strong><span id="broadcastLength"></span><button type="button" data-act="close" style="margin-left:auto">收起</button></div>
                <label for="broadcastScript">播报稿 · 可编辑后生成音频</label><textarea id="broadcastScript" maxlength="6000"></textarea>
                <div class="broadcast-controls"><button type="button" data-act="generate">生成音频</button><button type="button" data-act="read">设备朗读</button><button type="button" data-act="pause">暂停 / 继续</button><button type="button" data-act="stop">停止</button>
                <label>语速 <select id="broadcastRate"><option value="0.8">0.8×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option></select></label>
                <label>设备声音 <select id="broadcastVoice"></select></label></div>
                <audio id="broadcastAudio" controls hidden preload="metadata"></audio>
                <div class="broadcast-controls"><button type="button" data-act="text">下载文稿</button><a id="broadcastDownload" hidden download="deepsee-broadcast.mp3">下载音频</a></div>
                <p id="broadcastStatus" role="status"></p><small>设备朗读使用系统或浏览器提供的声音；在线声音可能需要联网。修改文稿后请重新生成音频。</small>`;
            const host = anchor?.closest('.module-panel') || anchor?.parentElement?.parentElement;
            (host || document.getElementById('ai-analysis') || document.body).appendChild(panel);
            panel.addEventListener('click', e => { const action = e.target.closest('[data-act]')?.dataset.act; if (action) act(action); });
            $('broadcastRate').onchange = () => { $('broadcastAudio').playbackRate = Number($('broadcastRate').value); };
            $('broadcastScript').oninput = () => { stop(); $('broadcastAudio').hidden = true; $('broadcastDownload').hidden = true; $('broadcastStatus').textContent = '文稿已修改，请重新生成音频或使用设备朗读。'; };
            window.speechSynthesis?.addEventListener('voiceschanged', voices);
        }
        panel.hidden = false; duration = result.duration_minutes || 5;
        $('broadcastScript').value = result.script || '';
        $('broadcastLength').textContent = `目标 ${duration} 分钟 · ${String(result.script || '').length} 字`;
        $('broadcastAudio').hidden = true; $('broadcastAudio').removeAttribute('src');
        $('broadcastDownload').hidden = true;
        $('broadcastStatus').textContent = '先核对文稿，再选择生成音频或设备朗读。';
        voices(); panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    async function act(action) {
        const script = $('broadcastScript').value.trim(), status = $('broadcastStatus');
        if (action === 'close') { stop(); panel.hidden = true; return; }
        if (action === 'stop') { stop(); status.textContent = '已停止'; return; }
        if (action === 'text') { download(new Blob([script], {type:'text/plain;charset=utf-8'}), 'deepsee-broadcast.txt'); return; }
        if (action === 'pause') {
            if (utterance) { if (speechSynthesis.paused) speechSynthesis.resume(); else speechSynthesis.pause(); }
            else if (!$('broadcastAudio').hidden) { const audio = $('broadcastAudio'); if (audio.paused) audio.play().catch(e => status.textContent = e.message); else audio.pause(); }
            return;
        }
        if (!script) { status.textContent = '请先填写播报稿'; return; }
        if (action === 'read') {
            if (!window.speechSynthesis) { status.textContent = '当前浏览器不支持设备朗读，请生成音频或下载文稿。'; return; }
            stop(); utterance = new SpeechSynthesisUtterance(script); utterance.lang = 'zh-CN';
            utterance.voice = speechSynthesis.getVoices().find(v => v.voiceURI === $('broadcastVoice').value) || null;
            utterance.rate = Number($('broadcastRate').value);
            utterance.onend = () => { utterance = null; status.textContent = '朗读结束'; };
            utterance.onerror = e => { utterance = null; status.textContent = '设备朗读未完成：' + e.error; };
            speechSynthesis.speak(utterance); status.textContent = '正在朗读'; return;
        }
        if (action !== 'generate' || synthesizing) return;
        synthesizing = true; const button = panel.querySelector('[data-act="generate"]'); button.disabled = true;
        status.textContent = '正在合成音频…';
        try {
            const r = await fetch('/api/ai/onepage-audio', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({script, duration_minutes:duration})});
            const d = await r.json();
            if (!r.ok || d.status !== 'ok' || !d.b64_audio) throw Error(d.error || d.detail || '语音服务暂不可用，可使用设备朗读。');
            if ($('broadcastScript').value.trim() !== script) { status.textContent = '文稿已变化，请重新生成。'; return; }
            if (objectURL) URL.revokeObjectURL(objectURL);
            const raw = atob(d.b64_audio.replace(/^data:[^,]+,/, ''));
            objectURL = URL.createObjectURL(new Blob([Uint8Array.from(raw, c => c.charCodeAt(0))], {type:d.mime_type || 'audio/mpeg'}));
            $('broadcastAudio').src = objectURL; $('broadcastAudio').hidden = false; $('broadcastAudio').playbackRate = Number($('broadcastRate').value);
            $('broadcastDownload').href = objectURL; $('broadcastDownload').hidden = false;
            status.textContent = '音频已生成，点击播放器试听。';
        } catch (e) { status.textContent = e.message; }
        finally { synthesizing = false; button.disabled = false; }
    }
    window.DeepseeBroadcast = {open, busy:false};
})();
