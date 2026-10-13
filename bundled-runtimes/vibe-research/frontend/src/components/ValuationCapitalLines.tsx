import {LINE_TREATMENTS, summarizeCapitalLines, type CapitalLineItem} from '@/lib/valuationCapitalLines';
import type {CapitalField} from '@/lib/valuationReview';

const cell = 'w-full rounded border border-border bg-card px-2 py-1.5 text-sm disabled:opacity-50';

export function ValuationCapitalLines({items, field, cashBasis, current, disabled, onChange}: {
  items: CapitalLineItem[]; field: CapitalField; cashBasis?: string; current: number|null|undefined; disabled: boolean;
  onChange?: (items: CapitalLineItem[])=>void;
}) {
  const summary = summarizeCapitalLines(items,field,cashBasis);
  const update = (id: string, patch: Partial<CapitalLineItem>)=>onChange?.(items.map(row=>row.id===id?{...row,...patch}:row));
  return <section aria-label="资本调整明细" className="space-y-2 text-sm">
    <p className="text-muted-foreground">单位：百万元 · 各行定位对应本次来源材料。纳入项相加，扣除项只减已包含的金额；“仅记录”不加也不减。合计行与其明细不能同时纳入。</p>
    <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-left" aria-label="资本调整明细表">
      <thead><tr className="text-muted-foreground"><th className="w-[18%] py-2">项目</th><th className="w-[18%]">处理方式</th><th className="w-[14%]">金额</th><th className="w-[20%]">文件 / 页码 / 附注</th><th>处理理由与范围</th>{onChange&&<th className="w-14">操作</th>}</tr></thead>
      <tbody>{items.map((row,index)=><tr key={row.id} className="border-t border-border align-top">
        <td className="py-2 pr-2">{onChange?<input className={cell} aria-label={`明细 ${index+1} 项目`} maxLength={160} value={row.label} disabled={disabled} onChange={e=>update(row.id,{label:e.target.value})}/>:row.label}</td>
        <td className="py-2 pr-2">{onChange?<select className={cell} aria-label={`明细 ${index+1} 处理方式`} value={row.treatment} disabled={disabled} onChange={e=>update(row.id,{treatment:e.target.value as CapitalLineItem['treatment']})}>
          {Object.entries(LINE_TREATMENTS).map(([value,label])=><option key={value} value={value} disabled={value==='deduct'&&field==='cashM'&&cashBasis==='gross'}>{label}</option>)}
        </select>:LINE_TREATMENTS[row.treatment]}</td>
        <td className="py-2 pr-2 tabular-nums">{onChange?<input className={cell} aria-label={`明细 ${index+1} 金额`} type="number" min="0" step="any" value={row.amountM??''} disabled={disabled} onChange={e=>update(row.id,{amountM:e.target.value===''?null:Number(e.target.value)})}/>:row.amountM?.toLocaleString('zh-CN',{maximumFractionDigits:8})??'缺失'}</td>
        <td className="py-2 pr-2">{onChange?<textarea className={cell} rows={2} aria-label={`明细 ${index+1} 来源定位`} maxLength={240} value={row.locator} disabled={disabled} onChange={e=>update(row.id,{locator:e.target.value})}/>:row.locator}</td>
        <td className="py-2 pr-2">{onChange?<textarea className={cell} rows={2} aria-label={`明细 ${index+1} 处理理由`} maxLength={500} value={row.reason} disabled={disabled} onChange={e=>update(row.id,{reason:e.target.value})}/>:row.reason}</td>
        {onChange&&<td className="py-2"><button className="text-muted-foreground underline disabled:opacity-50" aria-label={`移除明细 ${index+1}`} disabled={disabled} onClick={()=>onChange(items.filter(item=>item.id!==row.id))}>移除</button></td>}
      </tr>)}</tbody>
    </table></div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p aria-label="资本明细合计">明细合计：{summary.total===null?'待补齐':`${summary.total.toLocaleString('zh-CN',{maximumFractionDigits:8})} 百万元`}
        {summary.total!==null&&typeof current==='number'&&` · 当前值 ${current} · 差额 ${(summary.total-current).toLocaleString('zh-CN',{maximumFractionDigits:8})}`}</p>
      {onChange&&<button className="rounded border border-border px-3 py-2 disabled:opacity-50" disabled={disabled||items.length>=12} onClick={()=>onChange([...items,{id:crypto.randomUUID(),label:'',amountM:null,treatment:'add',locator:'',reason:''}])}>添加明细</button>}
    </div>
    {summary.issues.length>0&&<p className="text-warning" role="status">{summary.issues[0]}</p>}
    {onChange&&<p className="text-muted-foreground">编辑中的明细尚未采用，不影响当前估值；确认后才替换该项数值，随后请保存模型。</p>}
  </section>;
}
