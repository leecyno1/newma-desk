import {expect,it} from 'vitest';
import {emptyLinks,linkState,readLinks,saveLink,type CompanyLink} from './companyLinks';
import type {CompanyWorkbook} from './company';
import type {Snapshot} from './research';
const link:CompanyLink={industry:'合成行业',workbookId:'book',reason:'合成业务依据',reviewedAt:'2026-10-19T00:00:00Z',sourceRevision:2,
  security:{name:'合成公司',symbol:'000001',market:'CN',currency:'CNY'},fiscalPeriod:{label:'2025年报',periodEnd:'2025-12-31',basis:'annual'},
  workbookUpdatedAt:'2026-10-18',report:{url:'https://example.com/report',periodEnd:'2026-08-31'}};
const workbook:CompanyWorkbook={id:'book',updatedAt:link.workbookUpdatedAt,mode:'reported',security:link.security,fiscalPeriod:link.fiscalPeriod,metrics:[],sourceMaterials:[]};
const report={sourceUrl:link.report.url,periodEnd:link.report.periodEnd} as Snapshot;
it('关联保存按行业和底稿定位，更新不覆盖其他行业，也不复制财务值',()=>{
  const first=saveLink(emptyLinks(),link);
  const second=saveLink(first,{...link,industry:'另一个行业'});
  const updated=saveLink(second,{...link,reason:'修订依据',sourceRevision:3});
  expect(updated.entries).toHaveLength(2);
  expect(updated.entries[0]!.reason).toBe('修订依据');
  expect(updated.entries[1]!.reason).toBe(link.reason);
  expect(readLinks(JSON.parse(JSON.stringify(updated)))).toEqual(updated);
  expect(updated.entries[0]).not.toHaveProperty('metrics');
  expect(()=>readLinks({...first,entries:[link,link]})).toThrow();
});
it('底稿缺失、版本和行业报告变化须复核，版本一致也不自动确认',()=>{
  expect(linkState(link,undefined,report)).toContain('待读取');
  expect(linkState(link,[],report)).toContain('已删除');
  expect(linkState(link,[workbook],report)).toContain('仍须确认');
  for (const patch of [{updatedAt:'2026-10-19'},{mode:'preview'},{security:{...link.security,symbol:'000002'}},{fiscalPeriod:{...link.fiscalPeriod,periodEnd:'2024-12-31'}}]) {
    expect(linkState(link,[{...workbook,...patch}],report)).toContain('底稿已变更');
  }
  expect(linkState(link,[workbook],{...report,sourceUrl:'https://example.com/new'})).toContain('报告已切换');
});
