export type OutflowAllocation={account:string;amount:number|null};
export function OutflowAllocations({items,total,currency,onChange}:{items:OutflowAllocation[];total:number;currency:string;onChange(items:OutflowAllocation[]):void}){
  const assigned=items.reduce((sum,item)=>sum+(item.amount??0),0);
  return <details className="diagnosis-help"><summary>近期预留分配到账户{items.length?` · ${items.length} 项`:''}</summary>
    <p>总预留 {total.toLocaleString('zh-CN')} · 已分配 {assigned.toLocaleString('zh-CN')} · 待分配 {(total-assigned).toLocaleString('zh-CN')} {currency}。分配是拆分总额，不是额外支出。</p>
    {items.map((item,i)=><div className="diagnosis-fields" key={i}><label>预留 {i+1} 账户<input value={item.account} onChange={e=>onChange(items.map((a,j)=>j===i?{...a,account:e.target.value}:a))}/></label><label>预留 {i+1} 金额（{currency}）<input type="number" min={0} step="any" value={item.amount??''} onChange={e=>onChange(items.map((a,j)=>j===i?{...a,amount:e.target.value===''?null:Number(e.target.value)}:a))}/></label><button type="button" className="secondary-button" onClick={()=>onChange(items.filter((_,j)=>j!==i))}>移除预留 {i+1}</button></div>)}
    <button type="button" className="secondary-button" disabled={items.length>=2000} onClick={()=>onChange([...items,{account:'',amount:null}])}>分配账户预留</button>
    <p className="method-note">只填写尚未从可用现金中扣除的未来预留，避免重复。账户名称须与持仓一致，金额均为组合基准币等值；不能保证账户内可即时换汇。合计不得超过总预留。同一账户仅填一项；没有可用现金证据的账户仍为未评估。删除分配只将该笔退回未分配总额，不会减少总预留。</p>
  </details>;
}
