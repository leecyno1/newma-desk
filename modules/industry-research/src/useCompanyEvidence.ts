import { useEffect, useMemo, useState } from "react";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import type { Industry, Snapshot } from "./research";
import { companyFor, companyRevenueGroups, type CompanyInputs } from "./company";
import {compareRevenue,sameCompany} from './revenueComparison';
import {linkState, saveLink, type CompanyLink} from './companyLinks';
import {useCompanyLinks} from './useCompanyLinks';

type Host = Extract<ModHostConnection, {embedded: true}>;
const evidenceScope = (config?: Host['config']) => config ? JSON.stringify([
  config.user.id, config.workspace.id, config.instanceId, config.modId, config.gateways.data,
  config.session?.id, config.grants.permissions.includes('storage.read'),
]) : '';
export function useCompanyEvidence(host: Host | undefined, report: Snapshot | null, industry: Industry | undefined) {
  const links = useCompanyLinks(host);
  const [config, setConfig] = useState<Host['config']>();
  useEffect(() => {
    if (!host) {setConfig(undefined); return;}
    setConfig(host.config); return host.subscribe(setConfig);
  }, [host]);
  const identity = config ? {user: config.user.id, workspace: config.workspace.id} : undefined;
  const scope = evidenceScope(config);
  const [request, setRequest] = useState({scope: "", count: 0});
  const [result, setResult] = useState<{scope: string; status: string; data: CompanyInputs | null; error: string}>({scope: "", status: "idle", data: null, error: ""});
  const [choice, setChoice] = useState({key: "", id: ""});
  const [association, setAssociation] = useState({key: "", text: "", confirmed: false});
  useEffect(() => {
    if (!host || !scope || !request.count || request.scope !== scope) return;
    const controller = new AbortController();
    setResult({scope, status: "loading", data: null, error: ""});
    const current = () => !controller.signal.aborted && evidenceScope(host.config) === scope;
    void (async () => {
      const active = host.config;
      if (!current()) return;
      if (!active.session?.accessToken || !active.instanceId || !active.grants.permissions.includes('storage.read') || !active.gateways.data) {
        throw new Error('当前页面没有财报读取权限，请更新模组并重新打开');
      }
      const response = await fetch(new URL('/api/research-archive/industry-inputs', active.gateways.data), {
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]), cache: 'no-store',
        headers: {Authorization: `Bearer ${active.session.accessToken}`, 'X-Newma-Desk-Instance-Id': active.instanceId},
      });
      if (!response.ok) throw new Error('底稿读取失败，请核对权限和服务后重试');
      const data = await response.json() as CompanyInputs;
      if (!Number.isInteger(data?.revision) || data.revision < 0 || !Array.isArray(data.workbooks)
          || data.workbooks.some(row => !row || typeof row.id !== 'string' || !row.security || !row.fiscalPeriod
            || !Array.isArray(row.metrics) || !Array.isArray(row.sourceMaterials))) throw new Error('底稿格式异常，未采用任何证据');
      if (current()) setResult({scope, status: 'ready', data, error: ''});
    })().catch(error => {if (current()) setResult({scope, status: 'failed', data: null, error: error instanceof Error ? error.message : '底稿读取失败'});});
    return () => controller.abort();
  }, [host, scope, request]);
  const visible = result.scope === scope && scope ? result : {status: "idle", data: null, error: ""};
  const key = JSON.stringify([scope, request.count, visible.data?.revision, report?.sourceUrl, report?.periodEnd, report?.fetchedAt, industry?.name]);
  useEffect(() => {setChoice({key: "", id: ""}); setAssociation({key: "", text: "", confirmed: false});}, [key]);
  const selectedId = choice.key === key ? choice.id : "";
  const selected = visible.data?.workbooks.find(row => row.id === selectedId);
  const relationKey = `${key}|${selectedId}`;
  const reason = association.key === relationKey ? association.text : "";
  const confirmed = association.key === relationKey && association.confirmed;
  const revision = visible.data?.revision ?? 0;
  const evidence = useMemo(() => companyFor(report, industry, selected, confirmed ? reason : "", revision), [report, industry, selected, confirmed, reason, revision]);
  const comparisonKey=JSON.stringify([relationKey,reason,confirmed]);
  const blankComparison={key:comparisonKey,priorId:'',currentSourceId:'',priorSourceId:'',confirmedAt:''};
  const [comparisonChoice,setComparisonChoice]=useState(blankComparison);
  useEffect(()=>{setComparisonChoice({key:comparisonKey,priorId:'',currentSourceId:'',priorSourceId:'',confirmedAt:''});},[comparisonKey]);
  const comparisonChoiceVisible=comparisonChoice.key===comparisonKey?comparisonChoice:blankComparison;
  const comparisonBooks=useMemo(()=>selected?visible.data?.workbooks.filter(row=>row.id!==selected.id&&sameCompany(selected,row)&&row.mode==='reported'&&row.fiscalPeriod.basis==='annual'
    &&!!row.fiscalPeriod.periodEnd&&!!selected.fiscalPeriod.periodEnd&&row.fiscalPeriod.periodEnd<selected.fiscalPeriod.periodEnd)??[]:[],[selected,visible.data]);
  const priorBook=comparisonBooks.find(row=>row.id===comparisonChoiceVisible.priorId);
  const priorGroups=useMemo(()=>priorBook?companyRevenueGroups(priorBook):[],[priorBook]);
  const comparison=useMemo(()=>selected&&priorBook&&confirmed?compareRevenue(selected,priorBook,comparisonChoiceVisible.currentSourceId,comparisonChoiceVisible.priorSourceId,!!comparisonChoiceVisible.confirmedAt):null,
    [selected,priorBook,confirmed,comparisonChoiceVisible.currentSourceId,comparisonChoiceVisible.priorSourceId,comparisonChoiceVisible.confirmedAt]);
  const savedLinks = useMemo(() => links.status === 'ready' ? links.book.entries.filter(row=>row.industry===industry?.name)
    .map(row=>({...row,state:linkState(row,visible.data?.workbooks,report)})) : [],[links.status,links.book,industry?.name,visible.data,report]);
  const context = useMemo(() => ({status: visible.status, error: visible.error, evidence,revenueComparison:comparison,
    savedLinks:{status:links.status,revision:links.revision,entries:savedLinks,boundary:'已保存人工关联，仅作待核验线索，不等于当前有效公司证据。'}}), [visible.status, visible.error, evidence,comparison, links.status,links.revision,savedLinks]);
  return {...visible, available: !!identity, identity, selectedId, reason, confirmed, evidence, context, links, savedLinks, viewKey:key,
    comparison,comparisonBooks,priorGroups,comparisonChoice:comparisonChoiceVisible,
    chooseComparison(field:'priorId'|'currentSourceId'|'priorSourceId',value:string) {
      setComparisonChoice({...comparisonChoiceVisible,[field]:value,...(field==='priorSourceId'?{}:{priorSourceId:''}),confirmedAt:''});
    },
    confirmComparison(checked:boolean) {setComparisonChoice({...comparisonChoiceVisible,confirmedAt:checked?new Date().toISOString():''});},
    reloadLinks() {setAssociation(value=>({...value,confirmed:false})); return links.load();},
    restore(link:CompanyLink) {
      if (link.industry!==industry?.name || !visible.data?.workbooks.some(row=>row.id===link.workbookId)) return;
      setChoice({key,id:link.workbookId}); setAssociation({key:`${key}|${link.workbookId}`,text:link.reason,confirmed:false});
    },
    async saveAssociation() {
      if (!confirmed || !selected || !report || !industry || selected.mode!=='reported') return false;
      const saved = await links.save(saveLink(links.book,{industry:industry.name,workbookId:selected.id,reason,reviewedAt:new Date().toISOString(),
        security:selected.security,fiscalPeriod:selected.fiscalPeriod,workbookUpdatedAt:selected.updatedAt,sourceRevision:revision,
        report:{url:report.sourceUrl,periodEnd:report.periodEnd}}));
      if (!saved) setAssociation(value=>value.key===relationKey?{...value,confirmed:false}:value);
      return saved;
    },
    load() {setAssociation({key: "", text: "", confirmed: false}); setResult({scope, status: "loading", data: null, error: ""}); setRequest(value => ({scope, count: value.count + 1}));},
    select(id: string) {setChoice({key, id}); setAssociation({key: "", text: "", confirmed: false});},
    editReason(text: string) {setAssociation({key: relationKey, text, confirmed: false});},
    confirm() {if (selected && reason.trim()) setAssociation({key: relationKey, text: reason.trim(), confirmed: true});},
  };
}
