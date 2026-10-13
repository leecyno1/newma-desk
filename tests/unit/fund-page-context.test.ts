import {describe,it,expect} from 'vitest';
import {buildFundResearchPageContext,fundResearchWorkspaces,fundDiscoverDeskHref,fundDeskDestination} from '../../bundled-runtimes/fund-analysis/lib/newma-desk/context';
import {portfolioEvidence,portfolioHistoryVerified} from '../../bundled-runtimes/fund-analysis/lib/portfolio-evidence';

describe('portfolio evidence boundaries',()=>{
  it('does not accept legacy or cumulative-NAV calculations as verified history',()=>{
    expect(portfolioHistoryVerified({})).toBe(false);
    expect(portfolioHistoryVerified({methodology_version:'portfolio_adj_common_dates_v2',nav_basis:'accum_nav'})).toBe(false);
    expect(portfolioHistoryVerified({methodology_version:'portfolio_adj_common_dates_v2',nav_basis:'adj_nav'})).toBe(true);
  });
  const holdings=[{wind_code:'A',weight:0.6},{wind_code:'B',weight:0.4}];
  const targets=[{peer_group_key:'group',target_weight:1}];
  const monitor={status:'available',rebalance_needed:false,target_deviations:[{peer_group_key:'group',actual_weight:1,deviation:0,needs_rebalance:false}],style_drifts:[{wind_code:'A',status:'available',level:'low'},{wind_code:'B',status:'insufficient_evidence',level:'unavailable'}]};
  it('does not accept the old all-clear when only part of the fund evidence exists',()=>{
    const evidence=portfolioEvidence(holdings,targets,{A:0.6,B:0.4},monitor);
    expect(evidence.calculationMatchesSaved).toBe(true);
    expect(evidence.assessedWeight).toBe(0.6);
    expect(evidence.missingCodes).toEqual(['B']);
    expect(evidence.summary).toContain('不能判断为稳定');
    expect(evidence.rebalanceNeeded).toBe(false);
  });
  it('rejects partial weights even when the supplied weights sum to one',()=>{
    const evidence=portfolioEvidence([{wind_code:'A',weight:1},{wind_code:'B',weight:null}],targets,{A:1},monitor);
    expect(evidence.savedWeightsComplete).toBe(false);
    expect(evidence.calculationMatchesSaved).toBe(false);
    expect(evidence.assessedWeight).toBeNull();
    expect(evidence.rebalanceNeeded).toBeNull();
  });
  it('does not infer rebalance safety without complete targets and classifications',()=>{
    expect(portfolioEvidence(holdings,[],undefined,monitor).rebalanceNeeded).toBeNull();
    expect(portfolioEvidence(holdings,targets,undefined,{...monitor,target_deviations:[]}).rebalanceNeeded).toBeNull();
    expect(portfolioEvidence(holdings,targets,undefined,{...monitor,target_deviations:[...monitor.target_deviations,{peer_group_key:'unclassified',actual_weight:0.1,deviation:0.1,needs_rebalance:true}]}).rebalanceNeeded).toBeNull();
  });
});

describe('fund page evidence context',()=>{
  it('maps supported workflows with their parameters, without disguising unsupported routes',()=>{
    expect(fundDeskDestination('/analysis/advanced','?fundCode=000171.OF&quarter=2026Q2')?.href)
      .toBe('/mod/fund-research/advanced?fundCode=000171.OF&quarter=2026Q2');
    expect(fundDeskDestination('/managers/'+encodeURIComponent('经理|M|硕士'))?.search)
      .toBe(new URLSearchParams({view:'managers',managerId:'经理|M|硕士'}).toString());
    expect(fundDeskDestination('/compare','?codes=000171.OF,000001.OF')?.workspace).toBe('discover');
    expect(fundDeskDestination('/managers/compare','?manager_id=a&manager_id=b')?.search).toBe('manager_id=a&manager_id=b&view=manager-compare');
    expect(fundDeskDestination('/reports/test')?.search).toBe('view=report&reportId=test');
    expect(fundDeskDestination('/reports','search=test')?.search).toBe('search=test&view=reports');
    expect(fundDeskDestination('/reports/upload')).toBeNull();
    expect(fundDeskDestination('/reports/search')).toBeNull();
    expect(fundDeskDestination('/evidence-coverage','section=materials&codes=000001.OF')?.search).toBe('section=materials&codes=000001.OF&view=evidence');
    expect(fundDeskDestination('/alerts')?.search).toBe('view=evidence&section=review-events');
  });
  it('does not label capability descriptions as current research on any workspace',()=>{
    for(const workspace of fundResearchWorkspaces){
      const context=buildFundResearchPageContext({workspace});
      expect(context.data.freshness).toBe('unknown');
      expect(context.data.asOf).toBeUndefined();
      expect(context.data.summary?.contextStatus).toBe('capabilities-only');
      expect(context.data.summary?.page).toBeNull();
    }
  });
  it('retains applied filters separately from edited inputs and preserves missing values',()=>{
    const observation={selection:null,filters:{applied:{search:'000171'},form:{search:'005827'}},visibleBlocks:[{id:'results',type:'table'}],
      summary:{rows:[{symbol:'000171.OF',nav:null,navDate:null}],status:'loading',resultsArePrevious:true}};
    const context=buildFundResearchPageContext({workspace:fundResearchWorkspaces[0],selection:{symbol:'stale',assetType:'fund'},observation});
    expect(context.selection).toEqual({});
    expect(context.filters).toEqual(observation.filters);
    expect(context.data.summary?.page).toEqual(observation.summary);
    expect(context.visibleBlocks).toEqual(observation.visibleBlocks);
    expect(context.data.freshness).toBe('unknown');
  });
  it('uses the resolved detail identity and keeps different evidence dates separate',()=>{
    const observation={selection:{symbol:'000171.OF',name:'测试基金',assetType:'fund' as const},filters:{window:'3y'},visibleBlocks:[],
      summary:{fund:{navDate:'2026-09-11'},evaluation:{asOfDate:'2026-08-31'},holdings:{reportDate:'2026-06-30',announcementDate:'2026-08-28'}}};
    const context=buildFundResearchPageContext({workspace:fundResearchWorkspaces[0],selection:{symbol:'000171',assetType:'fund'},observation});
    expect(context.selection.symbol).toBe('000171.OF');
    expect(context.data.asOf).toBeUndefined();
    expect(context.data.summary?.page).toEqual(observation.summary);
  });
  it('keeps only supported list/detail routes in the same module without changing other workspaces',()=>{
    expect(fundDiscoverDeskHref('/funds/000171.OF')).toBe('/mod/fund-research/discover?symbol=000171.OF');
    expect(fundDiscoverDeskHref('/discover','?symbol=000171.OF&search=债券')).toBe('/mod/fund-research/discover?search=%E5%80%BA%E5%88%B8');
    expect(fundDiscoverDeskHref('/analysis')).toBeNull();
    expect(fundDiscoverDeskHref('/funds/a/b')).toBeNull();
  });
});
