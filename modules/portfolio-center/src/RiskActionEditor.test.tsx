import '@testing-library/jest-dom/vitest';
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { afterEach,expect,it,vi } from 'vitest';
import type { PortfolioRiskAction } from './types';
import { RiskActionEditor } from './RiskActionEditor';

const update=vi.hoisted(()=>vi.fn().mockResolvedValue({}));
vi.mock('./api',()=>({portfolioClient:()=>({updateRiskAction:update})}));
afterEach(()=>{cleanup();update.mockClear()});
const action:PortfolioRiskAction={id:'action',ruleId:'rule',severity:'high',title:'合成风险',detail:'原始依据',status:'acknowledged',owner:'合成负责人',note:'复核说明',dueAt:'2026-12-31T00:00:00Z',sourceSnapshotId:'source',createdAt:'2026-09-15T00:00:00Z',updatedAt:'2026-09-15T00:00:00Z'};

it('only persists an explicitly selected review when the user saves',async()=>{
  render(<RiskActionEditor action={action} identity={{userId:'u',workspaceId:'w'}} reviewCandidate={{id:'review',name:'新版本',asOf:'2026-09-15'}} onRefresh={()=>{}}/>);
  fireEvent.click(screen.getByRole('button',{name:'采用当前快照复核'}));
  expect(update).not.toHaveBeenCalled();
  expect(screen.getByText(/尚未保存/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'保存记录'}));
  await waitFor(()=>expect(update).toHaveBeenCalledWith('action',expect.objectContaining({reviewSnapshotId:'review',status:'acknowledged'})));
});

it('shows the stored review read-only after closure',()=>{
  render(<RiskActionEditor action={{...action,status:'resolved',reviewSnapshotId:'review'}} identity={{userId:'u',workspaceId:'w'}} reviewCandidate={{id:'other',name:'另一版本',asOf:'2026-09-15'}} onRefresh={()=>{}}/>);
  expect(screen.getByText(/复核快照：review/)).toBeVisible();
  expect(screen.queryByRole('button',{name:'采用当前快照复核'})).toBeNull();
  expect(screen.queryByRole('button',{name:'保存记录'})).toBeNull();
});
