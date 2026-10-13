type Issue={loc?:Array<string|number>;type?:string;msg?:string;ctx?:Record<string,unknown>};
const labels:Record<string,string>={navWarningFloor:'净值预警线',productId:'产品编号',name:'名称',asOf:'持仓截止日',baseCurrency:'基准币种',navFloor:'净值底线',nearTermOutflow:'近期需留资金',cashNeedDate:'资金观察日',assetType:'资产类型',market:'市场',symbol:'代码',account:'账户',currency:'币种',bookValue:'账面金额',fxToBase:'折算汇率',availableCash:'可用现金',equityBeta:'权益 Beta',equityBenchmark:'对冲基准',ratePnlPerBp:'整笔利率每基点损益',direction:'期货方向',notional:'名义金额',issuer:'发行人',source:'依据',modifiedDuration:'修正久期',contracts:'持仓手数',contractDv01:'每手 DV01',rateAsOf:'利率参数日期',expiryDate:'合约到期日',proceedsAmount:'预计到账金额',proceedsDate:'预计到账日',proceedsAccount:'收款账户',proceedsSource:'到账依据',label:'情景名称',equityShockPct:'权益变动（%）',rateShockBp:'利率变动（bp）',amount:'预留金额',text:'持仓表格',holdings:'持仓',additionalScenarios:'自定义情景',outflowAllocations:'账户预留'};
function message(issue:Issue){
  const type=issue.type||'';
  if(type==='missing'||type==='string_too_short')return '请填写此项';
  if(['float_parsing','float_type','int_parsing','int_type','int_from_float','finite_number'].includes(type))return type.startsWith('int')?'请填写整数':'请填写有效数字，不能以文字代替';
  if(type.startsWith('date_'))return '请使用有效日期（YYYY-MM-DD）';
  const bounds:Record<string,[string,string]>={greater_than:['gt','必须大于'],greater_than_equal:['ge','不能小于'],less_than:['lt','必须小于'],less_than_equal:['le','不能大于']};
  const bound=bounds[type];
  if(bound)return `${bound[1]} ${issue.ctx?.[bound[0]]}`;
  if(type==='string_too_long')return `最多填写 ${issue.ctx?.max_length} 个字符`;
  if(type==='too_long')return `最多允许 ${issue.ctx?.max_length} 项`;
  if(type==='too_short')return `至少需要 ${issue.ctx?.min_length} 项`;
  if(type==='literal_error')return '请选择支持的资产类型或期货方向';
  if(type==='string_pattern_mismatch')return '格式不正确；币种请填写 CNY、USD 等三位大写代码';
  if(type==='extra_forbidden')return '不支持此字段，请核对模板表头';
  return (issue.msg||'请检查输入格式').replace(/^Value error,\s*/,'');
}
export function formatImportError(detail:unknown,body?:unknown):string{
  if(typeof detail==='string')return detail;
  if(!Array.isArray(detail))return '请求未完成，请稍后重试；若持续失败请检查本地服务。';
  const model=body&&typeof body==='object'&&'holdings' in body?'PortfolioSnapshotInput':'PortfolioImportInput';
  const relevant=(detail as Issue[]).filter(e=>!(e.loc||[]).some(p=>typeof p==='string'&&/Portfolio(Import|Snapshot)Input/.test(p)&&!p.includes(model)));
  const lines=relevant.map(issue=>{
    const loc=(issue.loc||[]).filter(p=>p!=='body'&&!(typeof p==='string'&&p.includes('Portfolio')&&p.includes('Input'))).map(p=>typeof p==='string'?p.replace(/_([a-z])/g,(_,letter:string)=>letter.toUpperCase()):p);
    const section=loc[0];let prefix='组合';
    if(typeof loc[1]==='number')prefix=section==='csvRow'?`文件第 ${loc[1]} 行`:section==='holdings'?`持仓第 ${loc[1]+1} 行`:`${labels[String(section)]||section}第 ${loc[1]+1} 项`;
    const last=loc.at(-1);const field=typeof last==='string'?(labels[last]||last):'';
    return `${prefix}${field?' · '+field:''}：${message(issue)}`;
  });
  const unique=[...new Set(lines)];
  return unique.slice(0,8).join('\n')+(unique.length>8?`\n另有 ${unique.length-8} 项，请先修正上述问题后重新预览。`:'')||'请检查输入后重新预览。';
}
