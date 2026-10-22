import {describe, expect, it} from 'vitest';
import {businessRevenueSchema, summarizeBusinessRevenue, type BusinessRevenue} from './businessRevenue';

const row = (label:string,value:number) => ({label,value,rawValue:String(value),rawUnit:'亿元' as const,excerpt:`${label} ${value}`});
const group: BusinessRevenue = {reportId:'test',dimension:'product',title:'主营业务分产品情况',scope:'main-business',currency:'CNY',unit:'亿元',pdfPage:9,pdfPageCount:100,columnHeader:'营业收入 营业成本',rows:[row('甲',80),row('乙',20)],total:null,skippedRows:0,confirmedAt:'2026-10-19T00:00:00Z',contentOrigin:'pdf-text'};
describe('主营收入结构',()=>{
  it('无原表合计时只算已采用项目内占比，不声称占全公司',()=>{
    const result=summarizeBusinessRevenue(group);
    expect(result.denominatorLabel).toContain('非公司总收入');
    expect(result.rows.map(item=>item.sharePct)).toEqual([80,20]);
    expect(businessRevenueSchema.safeParse(group).success).toBe(true);
  });
  it('原表合计可覆盖未列明项目，不强行凑满100%',()=>{
    const result=summarizeBusinessRevenue({...group,total:row('合计',200),skippedRows:1});
    expect(result.denominatorLabel).toBe('原表合计');
    expect(result.rows.map(item=>item.sharePct)).toEqual([40,10]);
  });
  it('缺行、冲突、负数和零分母不生成误导占比',()=>{
    for(const patch of [{skippedRows:1},{total:row('合计',90)},{rows:[row('甲',-1)]},{rows:[row('甲',0)]}]) {
      const result=summarizeBusinessRevenue({...group,...patch});
      expect(result.reason).toBeTruthy();expect(result.rows.every(item=>item.sharePct===null)).toBe(true);
    }
    expect(businessRevenueSchema.safeParse({...group,rows:[row('甲',1),row('甲',2)]}).success).toBe(false);
    expect(businessRevenueSchema.safeParse({...group,pdfPage:101}).success).toBe(false);
  });
});
