export type AdditionalScenario={label:string;equityShockPct:number|null;rateShockBp:number|null};
export function SnapshotScenarios({items,onChange}:{items:AdditionalScenario[];onChange(items:AdditionalScenario[]):void}){
  const update=(index:number,field:keyof AdditionalScenario,value:string|number|null)=>onChange(items.map((s,i)=>i===index?{...s,[field]:value}:s));
  return <details className="diagnosis-help"><summary>自定义压力情景{items.length?` · ${items.length} 组`:''}</summary>
    <p>保留三组基础情景：权益 −10% / 利率 +50bp、权益 +10% / 利率 −50bp、权益 −10% / 利率 −50bp。最多追加 6 组，不替换基础压力测试。</p>
    {items.map((s,i)=><div key={i} className="diagnosis-fields"><label>情景 {i+1} 名称<input value={s.label} onChange={e=>update(i,'label',e.target.value)}/></label><label>情景 {i+1} 权益变动（%）<input type="number" min={-100} max={100} step="any" value={s.equityShockPct??''} onChange={e=>update(i,'equityShockPct',e.target.value===''?null:Number(e.target.value))}/></label><label>情景 {i+1} 利率变动（bp）<input type="number" min={-1000} max={1000} step="any" value={s.rateShockBp??''} onChange={e=>update(i,'rateShockBp',e.target.value===''?null:Number(e.target.value))}/></label><button type="button" className="secondary-button" onClick={()=>onChange(items.filter((_,j)=>i!==j))}>移除情景 {i+1}</button></div>)}
    <button type="button" className="secondary-button" disabled={items.length>=6} onClick={()=>{let n=1;while(items.some(s=>s.label===`补充压力 ${n}`))n++;onChange([...items,{label:`补充压力 ${n}`,equityShockPct:-20,rateShockBp:100}])}}>追加压力情景</button>
    <p className="method-note">权益单位为百分比（−20 表示下跌 20%），利率单位为基点（100bp = 1 个百分点），正值代表上行。是假设而非预测；冲击越大，一阶敏感度误差可能越大，不增加信用、基差或非线性建模。</p>
  </details>;
}
