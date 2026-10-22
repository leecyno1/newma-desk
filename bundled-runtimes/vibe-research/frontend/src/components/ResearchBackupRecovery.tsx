import { useEffect, useRef, useState } from 'react';
import { BACKUP_MAX_BYTES, parseResearchBackup, readLegacyResearchBackup, type ResearchBackup, type ResearchBackupKind, type ResearchBackupRow } from '@/lib/researchBackup';
import { getVibeDeskConfig } from '@/lib/vibedesk';

const control='rounded border border-border bg-card px-3 py-2 text-sm disabled:opacity-50';

export function ResearchBackupRecovery({kind,disabled,canRecover,onRecover}:{
  kind:ResearchBackupKind;disabled:boolean;canRecover:boolean;
  onRecover:(row:ResearchBackupRow)=>Promise<boolean>;
}) {
  const [open,setOpen]=useState(false);
  const [preview,setPreview]=useState<ResearchBackup|null>(null);
  const [label,setLabel]=useState('');
  const [selected,setSelected]=useState(0);
  const [confirmed,setConfirmed]=useState(false);
  const [restored,setRestored]=useState<number[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [downloadUrl,setDownloadUrl]=useState('');
  const input=useRef<HTMLInputElement>(null);
  const alive=useRef(true),request=useRef(0),locked=useRef(false),disabledRef=useRef(disabled);
  disabledRef.current=disabled;
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;request.current++}},[]);
  useEffect(()=>{
    if(!preview){setDownloadUrl('');return;}
    const url=URL.createObjectURL(new Blob([preview.raw],{type:'application/json'}));setDownloadUrl(url);
    return()=>URL.revokeObjectURL(url);
  },[preview]);
  const loaded=(value:ResearchBackup,name:string)=>{
    setPreview(value);setLabel(name);setSelected(0);setConfirmed(false);setRestored([]);setError('');
    setMessage(value.rows.length?`已预览 ${value.rows.length} 份，仅在浏览器内解析，尚未修改草稿或档案。`:'备份是空档案，没有可恢复内容。');
  };
  const readFile=async(file:File)=>{
    if(disabledRef.current||locked.current)return;
    if(file.size>BACKUP_MAX_BYTES){setError('文件超过 10MB，请分拆后读取。');return;}
    const id=++request.current;locked.current=true;setBusy(true);setError('');
    try {
      const raw=await file.text();
      if(!alive.current||id!==request.current)return;
      loaded(parseResearchBackup(raw,kind),file.name);
    } catch(error) {
      if(alive.current&&id===request.current)setError(error instanceof Error?error.message:'读取备份失败，原文件和当前草稿均未改动。');
    } finally {if(alive.current&&id===request.current){locked.current=false;setBusy(false)}}
  };
  const readLocal=(scoped:boolean)=>{
    if(disabledRef.current||locked.current)return;
    try{loaded(readLegacyResearchBackup(kind,scoped),scoped?'当前工作区旧缓存（归属仍须确认）':'本机未分区旧备份（归属未知）')}
    catch(error){setError(error instanceof Error?error.message:'读取旧备份失败，未改动原记录。')}
  };
  const recover=async()=>{
    if(!preview?.rows[selected]||disabledRef.current||!canRecover||!confirmed||locked.current||restored.includes(selected))return;
    locked.current=true;setBusy(true);setError('');
    try {
      if(await onRecover(preview.rows[selected])&&alive.current){
        setRestored(ids=>[...ids,selected]);setConfirmed(false);
        setMessage('已恢复为新的待保存草稿；恢复操作本身不写入档案。请检查正文后保存，当前是否已保存以顶部回执为准。原档案和旧备份保持不变。');
      }
    } catch(error){if(alive.current)setError(error instanceof Error?error.message:'恢复未完成，原档案和备份均保留。')}
    finally{if(alive.current){locked.current=false;setBusy(false)}}
  };
  const config=getVibeDeskConfig();
  return <section aria-label="备份恢复" className="mb-4 rounded-lg border border-border p-3 text-sm">
    <button className={control} disabled={disabled||busy} aria-expanded={open} onClick={()=>setOpen(!open)}>{open?'收起备份恢复':'恢复旧备份 / 导入草稿'}</button>
    {open&&<div className="mt-3 space-y-3">
      <p className="text-muted-foreground">先预览，再确认归属并恢复为新草稿；不自动同步、不按同名合并、不覆盖已保存档案。JSON 不包含原始 PDF，来源链接和确认状态需要重新核验。</p>
      <p>目标：{config?`Desk 工作区 ${config.workspaceId} · ${config.userId}`:'本机浏览器（尚未连接 Desk）'}。最终以顶部保存回执为准。</p>
      <div className="flex flex-wrap gap-2">
        <button className={control} disabled={disabled||busy} onClick={()=>input.current?.click()}>选择 JSON 备份</button>
        <input ref={input} type="file" accept=".json,application/json" aria-label="选择研究备份 JSON" className="hidden" disabled={disabled||busy} onChange={event=>{const file=event.target.files?.[0];if(file)void readFile(file);event.target.value=''}}/>
        {kind==='valuation'&&config&&<button className={control} disabled={disabled||busy} onClick={()=>readLocal(true)}>读取当前工作区旧缓存</button>}
        <button className={control} disabled={disabled||busy} onClick={()=>readLocal(false)}>读取本机未分区旧备份</button>
      </div>
      {busy&&<p role="status">正在处理备份…</p>}
      {error&&<p role="alert" className="text-destructive">{error}{preview&&' 下方仍是上次成功预览，不是本次失败文件。'}</p>}
      {message&&<p role="status">{message}</p>}
      {preview&&<>
        <p className="font-medium">预览来源：{label}</p>
        {preview.warnings.map(warning=><p key={warning} className="text-warning">{warning}</p>)}
        {!!preview.rows.length&&<>
          <label className="block">待恢复记录<select aria-label="待恢复备份记录" className={`${control} ml-2 max-w-full`} disabled={disabled||busy} value={selected} onChange={event=>{setSelected(Number(event.target.value));setConfirmed(false)}}>
            {preview.rows.map((row,index)=><option key={row.id} value={index}>{row.title} · {row.identity} · {row.asOf}{restored.includes(index)?' · 已取出草稿':''}</option>)}
          </select></label>
          <p className="break-words text-muted-foreground">原编号 {preview.rows[selected].id} · 备份内修改时间 {preview.rows[selected].updatedAt}（不是数据日期）</p>
          <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} disabled={disabled||busy} onChange={event=>setConfirmed(event.target.checked)}/>我确认此记录属于当前使用者及目标工作区；接受来源待复核，恢复为新副本。</label>
          <button className={control} disabled={disabled||busy||!confirmed||!canRecover||restored.includes(selected)} onClick={()=>void recover()}>恢复所选记录到新草稿</button>
          {!canRecover&&<p className="text-warning">请先完成当前档案读取并确认保存权限，恢复预览仍可查看或下载。</p>}
        </>}
        {downloadUrl&&<a download={`${kind}-original-backup.json`} href={downloadUrl} className="ml-3 text-primary underline">下载原始备份（含未采用内容）</a>}
        <details><summary className="cursor-pointer">查看原始备份及未采用内容</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{preview.raw}</pre></details>
      </>}
    </div>}
  </section>;
}
