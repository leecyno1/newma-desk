import {useEffect, useMemo, useRef, useState} from 'react';
import {createModStorageClientFromDesk, GatewayError, type ModHostConnection} from '@newma-desk/mod-sdk';
import {emptyLinks, readLinks, type CompanyLinks} from './companyLinks';
import {industryScope, hasIndustryGrant, privateIndustryFetch} from './industryAccess';

type Host = Extract<ModHostConnection, {embedded: true}>;
export function useCompanyLinks(host: Host | undefined) {
  const [config,setConfig] = useState<Host['config']>();
  useEffect(() => {if (!host) {setConfig(undefined); return;} setConfig(host.config); return host.subscribe(setConfig);},[host]);
  const scope = industryScope(config);
  const readable = hasIndustryGrant(config, 'storage.read');
  const writable = readable && hasIndustryGrant(config, 'storage.write');
  const client = useMemo(() => readable && config?.gateways.storage ? createModStorageClientFromDesk(config, privateIndustryFetch) : null,[config, readable]);
  const [state,setState] = useState({scope:'',status:'idle',book:emptyLinks(),revision:0,error:''});
  const active = useRef({scope,sequence:0,busy:false});
  if (active.current.scope !== scope) active.current = {scope,sequence:active.current.sequence+1,busy:false};
  useEffect(() => () => {active.current.sequence++;},[]);
  const visible = useMemo(() => state.scope === scope ? state : {scope,status:'idle',book:emptyLinks(),revision:0,error:''},[state,scope]);
  async function perform(next?: CompanyLinks) {
    if (!client || industryScope(host?.config) !== scope || !hasIndustryGrant(host?.config, next ? 'storage.write' : 'storage.read') || active.current.busy || next && (!writable || visible.status !== 'ready')) return false;
    const sequence = ++active.current.sequence; active.current.busy = true;
    const current = () => industryScope(host?.config) === scope && active.current.scope === scope && active.current.sequence === sequence;
    setState({...visible,status:next?'saving':'loading',error:''});
    try {
      let book: CompanyLinks, revision: number;
      if (next) {
        const result = await client.put('industry-tracking','company-links',readLinks(next),visible.revision);
        book = readLinks(result.value); revision = result.revision;
      } else {
        try {
          const result = await client.get('industry-tracking','company-links');
          book = readLinks(result.value); revision = result.revision;
        } catch (error) {
          if (!(error instanceof GatewayError) || error.status !== 404) throw error;
          book = emptyLinks(); revision = 0;
        }
      }
      if (!current()) return false;
      setState({scope,status:'ready',book,revision,error:''}); return true;
    } catch (error) {
      if (current()) setState({...visible,status:'failed',error:error instanceof GatewayError && error.status === 409
        ? '关联已在其他页面更新；草稿保留，请重新读取核对后再保存。'
        : error instanceof GatewayError ? '关联存储不可用，未确认保存；请重新读取核验。' : error instanceof Error ? error.message : '读取失败'});
      return false;
    } finally {if (current()) active.current.busy = false;}
  }
  return {...visible,writable,available:!!client,busy:['loading','saving'].includes(visible.status),load:()=>perform(),save:(book:CompanyLinks)=>perform(book)};
}
