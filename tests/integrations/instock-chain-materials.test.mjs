import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const html = readFileSync(join(root, 'instock/web/templates/industry_chain.html'), 'utf8');
const script = readFileSync(join(root, 'instock/web/static/js/industry-chain-materials.js'), 'utf8');
const data = {revision:1,workbooks:[{id:'synthetic',security:{name:'合成公司',symbol:'000001'},fiscalPeriod:{periodEnd:'2025-12-31'},sourceMaterials:[]}]};
function page() {
  const dom = new JSDOM(html,{url:'https://stock.test/mods/industry-chain',runScripts:'outside-only'});
  const {window}=dom;
  window.AbortController=AbortController;window.AbortSignal=AbortSignal;
  const bridge={config:{modId:'instock-industry-chain',instanceId:'frame',user:{id:'u'},workspace:{id:'w'},
    session:{id:'s',accessToken:'synthetic-token'},grants:{permissions:['analysis.read']},gateways:{data:'https://desk.test/api/data-services'}},whenReady:async()=>{}};
  const calls=[];window.fetch=async(...args)=>{calls.push(args);return new Response(JSON.stringify(data));};
  window.eval(script);
  return {dom,window,bridge,calls,materials:window.InStockChainMaterials({bridge,onChange(){}}),
    el:id=>window.document.getElementById(`chain-material-${id}`)};
}

test('materials use signed Desk identity; theme updates preserve loaded choices',async()=>{
  const p=page();try {
    await p.materials.read();
    assert.equal(p.calls[0][0],'https://desk.test/api/research-archive/industry-inputs');
    assert.deepEqual({...p.calls[0][1].headers},{Authorization:'Bearer synthetic-token','X-Newma-Desk-Instance-Id':'frame'});
    assert.equal(p.el('book').options.length,2);
    p.el('book').value='synthetic';p.bridge.config.environment={theme:'dark'};
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    assert.equal(p.el('book').value,'synthetic');assert.equal(p.calls.length,1);
    p.bridge.config.instanceId='new-frame';p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    assert.equal(p.el('book').options.length,1);assert.equal(p.el('confirm').checked,false);
  } finally {p.dom.window.close();}
});

test('materials do not call anonymous endpoints without the grant',async()=>{
  const p=page();try {
    p.bridge.config.grants.permissions=[];
    await p.materials.read();assert.equal(p.calls.length,0);
    assert.match(p.el('status').textContent,/已授权/);
  } finally {p.dom.window.close();}
});

test('late materials are ignored after workspace changes',async()=>{
  const p=page();try {
    let finish, bodyStarted;
    const body=new Promise(resolve=>{bodyStarted=resolve;});
    p.window.fetch=async()=>({ok:true,json:()=>new Promise(resolve=>{finish=resolve;bodyStarted();})});
    const reading=p.materials.read();await body;
    p.bridge.config.workspace={id:'other'};p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    finish(data);await reading;
    assert.equal(p.el('book').options.length,1);assert.match(p.el('status').textContent,/身份已变化/);
  } finally {p.dom.window.close();}
});

test('malformed projections are an error, not an empty workspace',async()=>{
  const p=page();try {
    p.window.fetch=async()=>new Response(JSON.stringify({revision:1,workbooks:[{}]}));
    await p.materials.read();assert.match(p.el('status').textContent,/格式异常/);
    assert.equal(p.el('book').options.length,1);
  } finally {p.dom.window.close();}
});

test('confirmed filing rows keep provenance and are discarded when the grant is revoked',async()=>{
  const p=page();try {
    const row={label:'合成业务',value:0,rawValue:'0',rawUnit:'元',excerpt:'合成业务 0 元，仅测试数据'};
    const book={...data.workbooks[0],mode:'reported',updatedAt:'2026-04-20T00:00:00Z',
      security:{name:'合成公司',symbol:'000001',market:'CN',currency:'CNY'},
      fiscalPeriod:{basis:'annual',periodEnd:'2025-12-31'},
      sourceMaterials:[{id:'filing',label:'合成年度原件',url:'https://example.test/filing.pdf',
        kind:'filing',status:'available',basis:'annual',periodEnd:'2025-12-31',
        businessRevenue:{contentOrigin:'pdf-text',scope:'main-business',currency:'CNY',unit:'亿元',
          dimension:'product',title:'合成主营收入',columnHeader:'项目 / 金额',
          confirmedAt:'2026-04-20T00:00:00Z',pdfPage:2,pdfPageCount:3,skippedRows:0,rows:[row]}}]};
    p.window.fetch=async()=>new Response(JSON.stringify({revision:2,workbooks:[book]}));
    await p.materials.read();
    for(const [field,value] of [['book','synthetic'],['source','filing'],['row','合成业务']]) {
      p.el(field).value=value;p.el(field).dispatchEvent(new p.window.Event('change'));
    }
    p.el('date').value='2026-04-20';
    assert.throws(()=>p.materials.material('2026-04-30','CN'),/先核对/);
    p.el('confirm').checked=true;
    const material=p.materials.material('2026-04-30','CN');
    assert.equal(material.row.value,0);
    assert.equal(material.sourceRevision,2);
    assert.equal(material.sourceUrl,'https://example.test/filing.pdf#page=2');
    assert.equal(p.materials.evidence(material).strength,'unverified');
    assert.equal(p.materials.context('2026-04-30','CN').status,'confirmed');
    assert.throws(()=>p.materials.material('2026-04-19','CN'),/披露日期/);
    p.bridge.config.grants.permissions=[];
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    assert.equal(p.el('confirm').checked,false);
    assert.equal(p.materials.material('2026-04-30','CN'),null);
    assert.equal(p.el('preview').textContent,'');
    assert.equal(p.materials.context('2026-04-30','CN').status,'empty');
  } finally {p.dom.window.close();}
});

test('standalone pages cannot read private workbooks using only claimed user IDs',async()=>{
  const p=page();try {
    delete p.bridge.config.session;
    await p.materials.read();
    assert.equal(p.calls.length,0);
    assert.match(p.el('status').textContent,/独立页不能读取/);
  } finally {p.dom.window.close();}
});
