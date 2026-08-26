// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import HistoryArchive from '@/components/orchestra/HistoryArchive';
import type { AgentProfile, DecisionEvent, RunSnapshot, RunSummary } from '@/types/orchestra';

const agent = {
  id: 'MACRO-01', name: '政策 林雅横', title: '政策', group: '宏观组', focus: '政策监控', persona: '', style: '', default_prompt: '',
  shared_skills: [], specialty_skills: [], skills: [], available_skills: [], missing_skills: [], research_channels: [], tushare_endpoints: [], outputs: [],
} satisfies AgentProfile;

const run = {
  id: 'run-1', topic: '光模块行业投资价值', mode: 'live', status: 'completed', phase: 'completed', created_at: '2026-07-24T00:00:00Z', updated_at: '2026-07-24T01:00:00Z',
  completed_agents: 19, total_agents: 19, error: null, owner_id: 'local-user', portfolio_id: null, parent_run_id: null, revision: 1, evidence_count: 74,
} satisfies RunSummary;

const snapshot = {
  ...run,
  last_event_seq: 3,
  agents: {},
  plan: '', consensus: '', decision: '', orchestra_thinking: '', orchestra_thinking_stage: null, revision_note: '', secret_refs: {},
} satisfies RunSnapshot;

const events = [
  { id: 'e1', run_id: run.id, seq: 1, type: 'agent.thinking', created_at: run.created_at, phase: 'research', agent_id: agent.id, payload: { summary: '核验政策传导路径' } },
  { id: 'e2', run_id: run.id, seq: 2, type: 'agent.tool.completed', created_at: run.created_at, phase: 'research', agent_id: agent.id, payload: { source: 'Tushare Pro', excerpt: '返回宏观数据' } },
  { id: 'e3', run_id: run.id, seq: 3, type: 'orchestra.decision', created_at: run.updated_at, phase: 'decision', agent_id: null, payload: { decision: '维持标配至小幅超配' } },
] satisfies DecisionEvent[];

describe('HistoryArchive', () => {
  it('shows persisted discussion events and filters the archive', async () => {
    const user = userEvent.setup();
    const onSelectRun = vi.fn();
    render(<HistoryArchive agents={[agent]} recentRuns={[run]} snapshot={snapshot} events={events} onSelectRun={onSelectRun} />);

    expect(screen.getByText('核验政策传导路径')).toBeTruthy();
    expect(screen.getByText('返回宏观数据')).toBeTruthy();
    expect(screen.getByText('维持标配至小幅超配')).toBeTruthy();

    await user.click(screen.getByRole('tab', { name: '数据' }));
    expect(screen.queryByText('核验政策传导路径')).toBeNull();
    expect(screen.getByText('返回宏观数据')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: /光模块行业投资价值/ }));
    expect(onSelectRun).toHaveBeenCalledWith('run-1');
  });
});
