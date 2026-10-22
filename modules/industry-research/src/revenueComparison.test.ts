import {expect,it} from 'vitest';
import {compareRevenue} from './revenueComparison';
import type {CompanyWorkbook} from './company';
import type {BusinessRevenue} from '@newma-desk/contracts';
function book(year:number,rows:[string,number][]):CompanyWorkbook {
  const group:BusinessRevenue={reportId:`pdf-${year}`,dimension:'product',title:'主营业务分产品情况',scope:'main-business',currency:'CNY',unit:'亿元',
    pdfPage:9,pdfPageCount:100,columnHeader:'营业收入 营业成本',rows:rows.map(([label,value])=>({label,value,rawValue:String(value),rawUnit:'亿元',excerpt:`${label} ${value}`})),
    total:null,skippedRows:0,confirmedAt:'2026-10-19T00:00:00Z',contentOrigin:'pdf-text'};
  return {id:`book-${year}`,updatedAt:'2026-10-19',mode:'reported',security:{name:'合成公司',symbol:'000001',market:'CN',currency:'CNY'},
    fiscalPeriod:{label:`${year}年报`,periodEnd:`${year}-12-31`,basis:'annual'},metrics:[],
    sourceMaterials:[{id:'products',kind:'filing',label:'合成原文',status:'available',periodEnd:`${year}-12-31`,basis:'annual',businessRevenue:group}]};
}
const compare=(a:CompanyWorkbook,b:CompanyWorkbook)=>compareRevenue(a,b,'products','products',true);
it('同口径跨期值和占比变化分开，未确认时不输出',()=>{
  const a=book(2025,[['甲',120],['乙',30]]),b=book(2024,[['甲',100],['乙',25]]);
  expect(compareRevenue(a,b,'products','products',false)).toBeNull();
  const result=compare(a,b)!;
  expect(result.rows[0]).toMatchObject({delta:20,changePct:20,shareChangePp:0});
  expect(result.changeLabel).toBe('同比变化');
  expect(compare(a,book(2023,[['甲',100],['乙',25]]))!.changeLabel).toContain('非同比');
});
it('不将更名当增长，缺失不补零；非正基数和负收入不输出普通增速',()=>{
  const result=compare(book(2025,[['甲新名',30],['零基数',10],['负收入',-5]]),book(2024,[['甲旧名',20],['零基数',0],['负收入',10]]))!;
  expect(result.rows.find(r=>r.label==='甲新名')).toMatchObject({prior:null,delta:null,changePct:null});
  expect(result.rows.find(r=>r.label==='甲旧名')).toMatchObject({current:null,delta:null});
  expect(result.rows.find(r=>r.label==='零基数')).toMatchObject({delta:10,changePct:null});
  expect(result.rows.find(r=>r.label==='负收入')).toMatchObject({delta:-15,changePct:null});
  expect(result.rows.every(r=>r.shareChangePp===null)).toBe(true);
  expect(result.shareReason).toContain('项目集合变化');
});
it('币种、身份、分类、年度及已采纳来源不满足时拒绝比较',()=>{
  const a=book(2025,[['甲',10]]),b=book(2024,[['甲',8]]);
  for(const patch of [{security:{...b.security,symbol:'000002'}},{security:{...b.security,currency:'USD'}},{mode:'preview'},{fiscalPeriod:{...b.fiscalPeriod,basis:'quarter'}}])expect(compare(a,{...b,...patch})).toBeNull();
  expect(compare(b,a)).toBeNull();expect(compare(a,a)).toBeNull();
  b.sourceMaterials[0]!.businessRevenue!.dimension='region';expect(compare(a,b)).toBeNull();
  b.sourceMaterials[0]!.businessRevenue!.dimension='product';b.sourceMaterials[0]!.status='unavailable';expect(compare(a,b)).toBeNull();
});
it('分母类型不同或存在漏行时不比较结构占比',()=>{
  const a=book(2025,[['甲',10]]),b=book(2024,[['甲',8]]);
  a.sourceMaterials[0]!.businessRevenue!.total={label:'合计',value:20,rawValue:'20',rawUnit:'亿元',excerpt:'合计 20'};
  expect(compare(a,b)!.rows[0]!.shareChangePp).toBeNull();
  expect(compare(a,b)!.shareReason).toContain('分母类型不同');
  a.sourceMaterials[0]!.businessRevenue!.skippedRows=1;
  expect(compare(a,b)!.shareReason).toContain('未识别行');
});
