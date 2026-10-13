export type Conclusion = {
  version:string; asOf:string; historical:boolean; headline:string;
  cashJudgment:string; navJudgment:string; boundary:string;
  findings:Array<{kind:string;title:string;detail:string;target:string;amount?:number;scenario?:string;account?:string;rowIndices?:number[]}>;
};

function reveal(target:string) {
  const element=document.getElementById(`diagnosis-${target}`);
  if(element instanceof HTMLDetailsElement)element.open=true;
  element?.scrollIntoView({behavior:'smooth',block:'start'});
  element?.focus({preventScroll:true});
}

export function PortfolioConclusion({data,currency,old}:{data:Conclusion;currency:string;old:boolean}) {
  return <section aria-label="组合风险结论" className="diagnosis-conclusion">
    <h3>组合风险结论</h3>
    {(old||data.historical)&&<p className="negative">历史快照：以下仅解释 {data.asOf} 的持仓，不能作为当前安全判断。</p>}
    <p><strong>{data.headline}</strong></p>
    <p>现金安全垫：{data.cashJudgment} · 净值安全垫：{data.navJudgment}</p>
    <ol>{data.findings.map((item,i)=><li key={`${item.kind}:${item.account||i}`}>
      <div className="diagnosis-conclusion-line"><strong>{item.title}{item.amount!=null&&` · 余量 ${item.amount.toLocaleString('zh-CN',{maximumFractionDigits:2})} ${currency}`}</strong><button className="secondary-button" onClick={()=>reveal(item.target)}>查看依据</button></div>
      {item.scenario&&<small>对应：{item.scenario}</small>}<p>{item.detail}</p>
    </li>)}</ol>
    <p className="method-note">{data.boundary}</p>
  </section>;
}
