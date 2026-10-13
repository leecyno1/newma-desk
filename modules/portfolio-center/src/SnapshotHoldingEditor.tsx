import { useState } from 'react';
import type { Holding } from './PortfolioDiagnosis';

type Field = {key:keyof Holding;label:string;type?:'number'|'date'};
const basics:Field[] = [
  {key:'name',label:'名称'},{key:'symbol',label:'代码'},{key:'market',label:'市场'},
  {key:'account',label:'账户'},{key:'currency',label:'币种'},
  {key:'bookValue',label:'账面金额',type:'number'},{key:'fxToBase',label:'折算汇率',type:'number'},
  {key:'issuer',label:'发行人'},{key:'source',label:'依据'},
];
const sensitivities:Field[] = [
  {key:'availableCash',label:'可用现金',type:'number'},
  {key:'equityBeta',label:'权益 Beta',type:'number'},{key:'equityBenchmark',label:'对冲基准'},
  {key:'ratePnlPerBp',label:'整笔利率每基点损益',type:'number'},
  {key:'modifiedDuration',label:'修正久期',type:'number'},
  {key:'notional',label:'名义金额',type:'number'},{key:'contracts',label:'持仓手数',type:'number'},
  {key:'contractDv01',label:'每手 DV01',type:'number'},
  {key:'rateAsOf',label:'利率参数日期',type:'date'},{key:'expiryDate',label:'合约到期日',type:'date'},
];
const receipts:Field[] = [
  {key:'proceedsAmount',label:'预计到账金额',type:'number'},
  {key:'proceedsDate',label:'预计到账日',type:'date'},
  {key:'proceedsAccount',label:'收款账户'},{key:'proceedsSource',label:'到账依据'},
];
const assets:Record<string,string>={stock:'股票',fund:'基金',bond:'债券',equity_future:'股指期货',bond_future:'国债期货',cash:'现金',liability:'负债',other:'其他'};

export function SnapshotHoldingEditor({holdings,onChange}:{holdings:Holding[];onChange(rows:Holding[]):void}) {
  const [index,setIndex]=useState(0);
  const [confirmRemove,setConfirmRemove]=useState(false);
  const [removed,setRemoved]=useState<{row:Holding;index:number}|null>(null);
  const row=holdings[index];
  const add=()=>{
    const blank:Holding={assetType:'other',market:'',symbol:'',name:'',account:row.account,currency:row.currency,
      bookValue:null,fxToBase:null,availableCash:null,equityBeta:null,equityBenchmark:'',ratePnlPerBp:null,
      direction:null,notional:null,source:'用户导入，未独立核验'};
    onChange([...holdings,blank]);setIndex(holdings.length);setConfirmRemove(false);
  };
  const remove=()=>{
    setRemoved({row:{...row},index});onChange(holdings.filter((_,i)=>i!==index));
    setIndex(Math.min(index,holdings.length-2));setConfirmRemove(false);
  };
  const undo=()=>{
    if(!removed)return;
    const position=Math.min(removed.index,holdings.length);
    const next=[...holdings];next.splice(position,0,removed.row);
    onChange(next);setIndex(position);setRemoved(null);setConfirmRemove(false);
  };
  const update=(key:keyof Holding,value:string|number|null)=>onChange(holdings.map((p,i)=>i===index?{...p,[key]:value}:p));
  const fields=(items:Field[])=><div className="diagnosis-fields">{items.map(f=><label key={f.key}>{f.label}{f.key==='source'||f.key==='proceedsSource'?<textarea rows={2} value={row[f.key]??''} onChange={e=>update(f.key,e.target.value)}/>:<input type={f.type||'text'} step={f.type==='number'?'any':undefined} value={row[f.key]??''} onChange={e=>update(f.key,f.type==='number'?(e.target.value===''?null:Number(e.target.value)):f.type==='date'?(e.target.value||null):e.target.value)}/>}</label>)}</div>;
  return <section aria-label="编辑原始持仓">
    <label>选择持仓<select value={index} onChange={e=>{setIndex(Number(e.target.value));setConfirmRemove(false)}}>{holdings.map((p,i)=><option key={i} value={i}>{i+1}. {p.name||'待填写持仓'} · {p.symbol||'未填代码'} · {p.account}</option>)}</select></label>
    <div className="diagnosis-toolbar"><button type="button" className="secondary-button" disabled={holdings.length>=2000} onClick={add}>新增持仓行</button><button type="button" className="secondary-button" disabled={holdings.length<=1} onClick={()=>setConfirmRemove(true)}>移除当前行</button>{removed&&<button type="button" className="secondary-button" disabled={holdings.length>=2000} onClick={undo}>撤销上次移除</button>}<span>至少保留一行，最多 2000 行；只编辑快照，不自动买卖或增减现金。</span></div>
    {confirmRemove&&<div role="group" aria-label="确认移除持仓"><p>从编辑副本移除「{row.name||'未命名'} · {row.symbol||'未填代码'} · {row.account}」？该行的敏感度及到账计划也会移出新版，旧快照不变。</p><button type="button" className="secondary-button" onClick={remove}>确认移除此行</button><button type="button" className="secondary-button" onClick={()=>setConfirmRemove(false)}>保留此行</button></div>}
    <p className="method-note">共 {holdings.length} 行。逐行补值，空白仍表示未知；原始参数和日期保留，不自动更新行情。清空字段也需重新预览。</p>
    <div className="diagnosis-fields"><label>资产类型<select value={row.assetType} onChange={e=>update('assetType',e.target.value)}>{Object.entries(assets).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>期货方向<select value={row.direction||''} onChange={e=>update('direction',e.target.value||null)}><option value="">未填写 / 非期货</option><option value="long">多头</option><option value="short">空头</option></select></label></div>
    {fields(basics)}
    <details><summary>风险参数与期限</summary>{fields(sensitivities)}</details>
    <details><summary>预计到账计划</summary>{fields(receipts)}</details>
  </section>;
}
