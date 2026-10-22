import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const source = name => readFileSync(join(root, 'instock/web/static/js', name), 'utf8');
const entry = (id = 'first') => ({id, decision:'insufficient', reviewedAt:'2026-10-19T01:00:00Z', snapshotId:'synthetic',
  target:{theme:'合成验收',market:'CN',asOf:'2026-10-19',source:{id:'up',name:'上游'},target:{id:'down',name:'下游'},relation:'合成关系',evidence:[]},
  sourceRef:'',sourceDate:'',locator:'',quote:'',note:'合成材料不足，不是投资结论',reviewerUserId:'standalone-browser-local'});
const book = (...entries) => ({schemaVersion:1,entries});
function page(bridge = {embedded:false}, html = '<main id="reader"></main>') {
  const dom = new JSDOM(html, {url:'http://localhost:19998',runScripts:'outside-only'});
  const {window} = dom;
  let pending = Promise.resolve();
  Object.defineProperty(window.navigator, 'locks', {configurable:true, value:{request(_name, action) {
    const result = pending.then(action); pending = result.catch(()=>{}); return result;
  }}});
  window.eval(source('industry-chain-review-contract.js'));
  window.eval(source('industry-chain-review-storage.js'));
  return {dom, window, bridge, store:window.InStockChainReviewStorage(bridge)};
}

test('standalone persists across adapters without fetching Desk', async()=>{
  const p = page(); try {
    p.window.fetch = ()=>{throw new Error('must not fetch');};
    assert.equal((await p.store.read()).revision,0);
    await p.store.write(0,book(entry()));
    const second = p.window.InStockChainReviewStorage(p.bridge);
    assert.equal((await second.read()).value.entries[0].id,'first');
    assert.equal(second.info().mode,'browser-local');
    assert.match(second.info().description,/不同步到 Desk/);
  } finally {p.dom.window.close();}
});

test('two stale writers cannot overwrite each other',async()=>{
  const p=page(); try {
    const other=p.window.InStockChainReviewStorage(p.bridge);
    const results=await Promise.allSettled([p.store.write(0,book(entry())),other.write(0,book(entry('second')))]);
    assert.equal(results.filter(row=>row.status==='fulfilled').length,1);
    assert.match(results.find(row=>row.status==='rejected').reason.message,/其他页面更新/);
    assert.equal((await p.store.read()).value.entries.length,1);
  } finally {p.dom.window.close();}
});

test('corrupt local data, missing locks and denied storage never report saved',async()=>{
  const p=page(); try {
    await p.store.write(0,book(entry()));
    const key=p.window.localStorage.key(0);
    p.window.localStorage.setItem(key,'{broken');
    await assert.rejects(p.store.read(),/格式异常/);
    await assert.rejects(p.store.write(0,book(entry('new'))),/格式异常/);
    assert.equal(p.window.localStorage.getItem(key),'{broken');
    p.window.localStorage.removeItem(key);
    Object.defineProperty(p.window.navigator,'locks',{value:undefined});
    assert.equal(p.store.info().canWrite,false);
    await assert.rejects(p.store.write(0,book(entry())),/安全写入锁/);
    Object.defineProperty(p.window,'localStorage',{get(){throw new Error('storage denied');}});
    await assert.rejects(p.store.read(),/本机存储不可用/);
  } finally {p.dom.window.close();}
});

test('embedded authorization failures never fall back to browser records',async()=>{
  const bridge={embedded:false}; const p=page(bridge); try {
    await p.store.write(0,book(entry()));
    bridge.embedded=true;
    assert.equal(p.store.info().canRead,false);
    await assert.rejects(p.store.read(),/Desk 会话/);
    bridge.config={user:{id:'u'},workspace:{id:'w'},instanceId:'frame',session:{accessToken:'test-only'},gateways:{storage:'https://desk.test/api/storage'}};
    let calls=0;
    p.window.fetch=async(_url,options)=>{calls++;assert.equal(options.headers.Authorization,'Bearer test-only');return {ok:false,status:403};};
    await assert.rejects(p.store.read(),/工作区存储不可用/);
    await assert.rejects(p.store.write(0,book(entry())),/工作区存储不可用/);
    assert.equal(calls,2);
    bridge.embedded=false;
    assert.equal((await p.store.read()).value.entries[0].id,'first');
  } finally {p.dom.window.close();}
});

test('local relation reader selects latest matching opinion and cannot certify Desk archives',async()=>{
  const p=page(); try {
    const latest=entry('latest');latest.archiveSource={text:'合成原文',workbookId:'w',sourceId:'s',pdfPage:1};
    const unrelated=entry('other');unrelated.target.theme='另一主题';
    await p.store.write(0,book(entry(),latest,unrelated));
    const result=await p.store.readRelations({theme:'合成验收',market:'CN',relations:[{source:'up',target:'down'}]});
    assert.deepEqual(Array.from(result.book.entries,row=>row.id),['latest']);
    assert.equal(result.archive.status,'unavailable');
    p.window.eval(source('stock-chain-reviews.js'));
    const reader=p.window.InStockStockChainReviews({bridge:p.bridge,root:p.window.document.getElementById('reader'),onChange(){},autoLoad:false});
    reader.setData({exposure:{},research_context:{theme:'合成验收',market:'CN',as_of:'2026-10-19',
      chain:{nodes:[{id:'up',name:'上游'},{id:'down',name:'下游'}],links:[{source:'up',target:'down',relation:'合成关系',evidence_ids:[]}]},evidence:[]}});
    await reader.refresh();
    assert.equal(reader.context().status,'ready');
    assert.equal(reader.context().relations[0].review.id,'latest');
    assert.equal(reader.context().relations[0].status,'needs-review');
    assert.equal(reader.context().storage.mode,'browser-local');
    assert.match(p.window.document.getElementById('reader').textContent,/不同步到 Desk/);
  } finally {p.dom.window.close();}
});

test('actual editor requires confirmation, persists, restores and preserves a conflicted draft',async()=>{
  const p=page({embedded:false},readFileSync(join(root,'instock/web/templates/industry_chain.html'),'utf8'));
  try {
    p.window.HTMLElement.prototype.scrollIntoView=()=>{};
    p.window.InStockChainSupport=()=>({sync(){},context(){return {};}});
    p.window.InStockChainArchive=()=>({clearSelection(){},isCurrent:()=>false,context(){return {};}});
    p.window.eval(source('industry-chain-reviews.js'));
    const editor=p.window.InStockChainReviews({bridge:p.bridge,onChange(){}});
    const el=id=>p.window.document.getElementById('chain-review-'+id);
    const settle=()=>new Promise(resolve=>setImmediate(resolve));
    editor.setData({theme:'合成验收',market:'CN',as_of:'2026-10-19',snapshot:{snapshot_id:'synthetic'},
      chain:{nodes:[{id:'up',name:'上游'},{id:'down',name:'下游'}],links:[{source:'up',target:'down',relation:'合成关系',evidence_ids:[]}]},evidence:[]});
    el('load').click(); await settle(); editor.select('up','down');
    el('note').value='合成验收：只验证保存，不是投资判断';el('note').dispatchEvent(new p.window.Event('input'));
    el('save').click(); await settle();
    assert.equal((await p.store.read()).value.entries.length,0);
    assert.match(el('status').textContent,/请确认/);
    el('confirm').checked=true;el('save').click();await settle();
    assert.equal(editor.context().savedCount,1);
    assert.equal(editor.context().storage.mode,'browser-local');
    assert.equal((await p.store.read()).value.entries[0].reviewerUserId,'standalone-browser-local');
    el('load').click();await settle();assert.match(el('list').textContent,/只验证保存/);
    const current=await p.store.read();
    await p.store.write(current.revision,book(...current.value.entries,entry('another-page')));
    el('note').value='另一页更新后，我的未保存草稿';el('note').dispatchEvent(new p.window.Event('input'));
    el('confirm').checked=true;el('save').click();await settle();
    assert.equal(editor.context().status,'failed');
    assert.match(el('status').textContent,/其他页面更新/);
    assert.equal(el('note').value,'另一页更新后，我的未保存草稿');
    assert.equal((await p.store.read()).value.entries.length,2);
    p.bridge.embedded=true;
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    assert.equal(editor.context().savedCount,null);
    assert.equal(el('note').value,'');assert.equal(el('load').disabled,true);
  } finally {p.dom.window.close();}
});

test('changed evidence removes untouched adopted advice but preserves an edited human opinion',async()=>{
  const p=page({embedded:false},readFileSync(join(root,'instock/web/templates/industry_chain.html'),'utf8'));
  try {
    let assistance;
    p.window.HTMLElement.prototype.scrollIntoView=()=>{};
    p.window.InStockChainSupport=options=>{assistance=options;return {sync(){},context(){return {};}};};
    p.window.InStockChainArchive=()=>({clearSelection(){},isCurrent:()=>false,context(){return {};}});
    p.window.eval(source('industry-chain-reviews.js'));
    const editor=p.window.InStockChainReviews({bridge:p.bridge,onChange(){}});
    const el=id=>p.window.document.getElementById('chain-review-'+id);
    const edit=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new p.window.Event('input'));};
    const settle=()=>new Promise(resolve=>setImmediate(resolve));
    editor.setData({theme:'合成验收',market:'CN',as_of:'2026-10-19',snapshot:{snapshot_id:'synthetic'},
      chain:{nodes:[{id:'up',name:'上游'},{id:'down',name:'下游'}],links:[{source:'up',target:'down',relation:'合成关系',evidence_ids:[]}]},evidence:[]});
    el('load').click();await settle();editor.select('up','down');
    edit('sourceRef','https://example.com/public');edit('sourceDate','2026-10-19');
    edit('locator','段落1');edit('quote','旧摘录');
    const apply=()=>assistance.onApply({input:{...assistance.getInput(),requestId:'test-only'},
      result:{verdict:'supported',explanation:'模型对旧摘录的理由',gaps:[]}});
    apply();assert.equal(el('decision').value,'supported');assert.match(el('note').value,/模型对旧摘录/);
    el('confirm').checked=true;edit('quote','新摘录，不说明供货关系');
    assert.equal(el('note').value,'');assert.equal(el('decision').value,'insufficient');
    assert.equal(el('confirm').checked,false);
    el('confirm').checked=true;el('save').click();await settle();
    assert.match(el('status').textContent,/请填写判断依据/);assert.equal((await p.store.read()).value.entries.length,0);
    apply();edit('decision','contradicted');edit('note','人工已改判：另有直接反证，需核对新原文。');
    edit('locator','段落2');
    assert.equal(el('decision').value,'contradicted');
    assert.equal(el('note').value,'人工已改判：另有直接反证，需核对新原文。');
  } finally {p.dom.window.close();}
});

test('Desk adapter keeps signed storage and relation routes and validates responses',async()=>{
  const bridge={embedded:true,config:{user:{id:'u'},workspace:{id:'w'},instanceId:'frame',session:{accessToken:'test-only'},gateways:{storage:'https://desk.test/api/mods/instock-industry-chain/storage'}}};
  const p=page(bridge);try {
    const calls=[];
    p.window.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({revision:1,value:book(entry())})};};
    await p.store.write(0,book(entry()));
    assert.equal(calls[0].url,'https://desk.test/api/mods/instock-industry-chain/storage/relation-reviews/records');
    assert.equal(calls[0].options.headers['X-Newma-Desk-Instance-Id'],'frame');
    assert.equal(JSON.parse(calls[0].options.body).expectedRevision,0);
    const input={theme:'合成验收',market:'CN',relations:[{source:'up',target:'down'}]};
    p.window.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({revision:1,book:book(entry()),archive:{status:'ready',materials:[]}})};};
    await p.store.readRelations(input);
    assert.equal(calls[1].url,'https://desk.test/api/mods/instock-industry-chain/sources/chain-reviews');
    p.window.fetch=async()=>({ok:false,status:404});
    assert.equal((await p.store.read()).revision,0);
    p.window.fetch=async()=>({ok:true,json:async()=>({revision:'bad',value:book()})});
    await assert.rejects(p.store.read(),/版本格式异常/);
  } finally {p.dom.window.close();}
});

test('quota failure and a scope switch while waiting for the lock do not write',async()=>{
  const p=page();try {
    p.window.Storage.prototype.setItem=()=>{throw new Error('quota');};
    await assert.rejects(p.store.write(0,book(entry())),/本机保存失败/);
    assert.equal((await p.store.read()).revision,0);
    let release;
    p.window.navigator.locks.request=(_name,action)=>new Promise((resolve,reject)=>{release=()=>{try{resolve(action());}catch(error){reject(error);}};});
    const waiting=p.store.write(0,book(entry()));
    p.bridge.embedded=true;release();
    await assert.rejects(waiting,/存储范围已变化/);
    p.bridge.embedded=false;
    assert.equal((await p.store.read()).revision,0);
  } finally {p.dom.window.close();}
});
