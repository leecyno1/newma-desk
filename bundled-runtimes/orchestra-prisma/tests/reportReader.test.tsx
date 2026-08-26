// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ReportReader from '@/components/orchestra/ReportReader';
import type { AgentProfile, RunArtifact, RunEvidence } from '@/types/orchestra';

const agent = {
  id: 'EQUITY-01', name: '科技成长 葛书明', title: '科技成长', group: '股票组', focus: '技术路线', persona: '', style: '', default_prompt: '',
  shared_skills: [], specialty_skills: [], skills: [], available_skills: [], missing_skills: [], research_channels: [], tushare_endpoints: [], outputs: [],
} satisfies AgentProfile;

const artifacts = [
  {
    id: 'a1', run_id: 'run-1', agent_id: agent.id, kind: 'research_report', title: '科技成长阶段成果', version: 1, created_at: '2026-07-24T00:00:00Z',
    content: '# 核心观点\n\n光模块景气延续。\n\n## 风险与反证\n\n| 指标 | 状态 |\n| --- | --- |\n| 估值 | 偏高 |',
  },
  {
    id: 'a2', run_id: 'run-1', agent_id: null, kind: 'decision', title: '正式投委会决议', version: 1, created_at: '2026-07-24T01:00:00Z', content: '# 决议\n\n维持标配。',
  },
] satisfies RunArtifact[];

const evidence = [{
  id: 'e1', run_id: 'run-1', agent_id: agent.id, source_name: 'Tushare Pro', source_url: null, observed_at: '20260724', retrieved_at: '2026-07-24T00:00:00Z', tool_name: 'tushare_query', interface_name: 'daily_basic', params: {}, status: 'success', excerpt: 'PE_TTM 估值数据', content_hash: '1234567890abcdef1234',
}] satisfies RunEvidence[];

describe('ReportReader', () => {
  it('renders Markdown, evidence, outline and report navigation', async () => {
    const user = userEvent.setup();
    const onSelectArtifact = vi.fn();
    render(
      <ReportReader
        artifact={artifacts[0]}
        artifacts={artifacts}
        evidence={evidence}
        snapshot={null}
        agents={[agent]}
        onSelectArtifact={onSelectArtifact}
        onExport={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getAllByText('核心观点').length).toBeGreaterThan(0);
    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByText('PE_TTM 估值数据')).toBeTruthy();
    expect(screen.getByText('科技成长 葛书明')).toBeTruthy();

    await user.click(screen.getByTitle('下一篇报告'));
    expect(onSelectArtifact).toHaveBeenCalledWith(artifacts[1]);
  });

  it('opens a two-column Markdown comparison without leaving the reader', async () => {
    const user = userEvent.setup();
    render(
      <ReportReader
        artifact={artifacts[0]}
        artifacts={artifacts}
        evidence={evidence}
        snapshot={null}
        agents={[agent]}
        onSelectArtifact={vi.fn()}
        onExport={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '并排比较报告' }));
    expect(screen.getByRole('main', { name: '报告并排比较' })).toBeTruthy();
    expect(screen.getByRole('combobox', { name: '选择对比报告' })).toBeTruthy();
    expect(screen.getAllByText('科技成长阶段成果').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正式投委会决议').length).toBeGreaterThan(0);
  });
});
