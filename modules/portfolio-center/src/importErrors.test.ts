import {expect,it} from 'vitest';
import {formatImportError} from './importErrors';

it('shows only the matching union branch without echoing full inputs',()=>{
  const issues=[{loc:['body','PortfolioImportInput','text'],type:'missing',msg:'Field required'},
    {loc:['body','function-after[check_snapshot(), PortfolioSnapshotInput]','holdings',1,'bookValue'],type:'float_parsing',input:'private holdings'},
    {loc:['body','function-after[check_snapshot(), PortfolioSnapshotInput]','holdings',1],type:'value_error',msg:'Value error, 可用现金不得超过账面金额'}];
  const text=formatImportError(issues,{holdings:[]});
  expect(text).toContain('持仓第 2 行 · 账面金额：请填写有效数字');
  expect(text).toContain('持仓第 2 行：可用现金不得超过账面金额');
  expect(text).not.toMatch(/Portfolio|private|持仓表格|Value error/);
});

it('labels CSV rows, nested assumptions and range limits',()=>{
  expect(formatImportError([{loc:['csvRow',4,'fxToBase'],type:'greater_than',ctx:{gt:0}}])).toBe('文件第 4 行 · 折算汇率：必须大于 0');
  expect(formatImportError([{loc:['body','PortfolioImportInput','additionalScenarios',0,'rateShockBp'],type:'less_than_equal',ctx:{le:1000}}],{text:'x'})).toBe('自定义情景第 1 项 · 利率变动（bp）：不能大于 1000');
  expect(formatImportError([{loc:['near_term_outflow'],type:'greater_than_equal',ctx:{ge:0}}])).toBe('组合 · 近期需留资金：不能小于 0');
});

it('preserves actionable server messages and keeps errors bounded',()=>{
  expect(formatImportError('账户预留合计不能超过近期需留资金总额')).toBe('账户预留合计不能超过近期需留资金总额');
  const issues=Array.from({length:10},(_,i)=>({loc:['csvRow',i+2,'name'],type:'missing'}));
  expect(formatImportError(issues)).toContain('另有 2 项');
});
