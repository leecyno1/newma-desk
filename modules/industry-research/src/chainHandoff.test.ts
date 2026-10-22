import {expect,it} from 'vitest';
import {chainHandoffUrl} from './chainHandoff';
import type {CompanyEvidence} from './company';

it('只传已确认关联的来源标识与工作区，不复制数值或冒充披露日期',()=>{
  const evidence={workbookId:'book&1',savedAt:'2026-10-19T01:00:00Z',industry:'测试行业',
    revenueGroups:[{sourceId:'source:1',group:{reportId:'pdf'}}]} as NonNullable<CompanyEvidence>;
  const base='http://127.0.0.1:5888/?mod=instock-industry-chain';
  const url=new URL(chainHandoffUrl(base,evidence,'source:1',{user:'u',workspace:'w'})!);
  const params=new URLSearchParams(url.searchParams.get('modSearch')!);
  expect(params.get('sourceWorkbookId')).toBe('book&1');
  expect(params.get('sourceId')).toBe('source:1');
  expect(params.get('sourceWorkspaceId')).toBe('w');
  expect(params.has('asOf')).toBe(false);
  expect(params.has('revenue')).toBe(false);
  expect(chainHandoffUrl(base,null,'source:1',{user:'u',workspace:'w'})).toBeNull();
  expect(chainHandoffUrl(base,evidence,'missing',{user:'u',workspace:'w'})).toBeNull();
  expect(chainHandoffUrl(base,evidence,'source:1')).toBeNull();
});
