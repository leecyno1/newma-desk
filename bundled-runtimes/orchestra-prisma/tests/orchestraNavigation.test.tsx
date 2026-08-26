// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  loadRun: vi.fn(),
  newRun: vi.fn(),
  refreshSystemData: vi.fn(),
  refreshProfiles: vi.fn(),
}));

const agent = {
  id: 'MACRO-01',
  name: '林雅横',
  title: '政策研究员',
  group: '宏观组',
  focus: '政策方向与流动性',
  persona: '审慎',
  style: '政策框架',
  default_prompt: '',
  shared_skills: ['finance-data-router', 'data-quality-checker'],
  specialty_skills: ['policy-monitor'],
  skills: ['policy-monitor'],
  available_skills: ['policy-monitor'],
  missing_skills: [],
  research_channels: ['Tushare'],
  tushare_endpoints: ['cn_m'],
  outputs: ['政策判断'],
};

const snapshot = {
  id: 'run-1',
  topic: '历史议题',
  mode: 'demo' as const,
  status: 'completed' as const,
  phase: 'completed',
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:01:00Z',
  last_event_seq: 120,
  agents: {
    'MACRO-01': {
      id: 'MACRO-01',
      status: 'completed' as const,
      phase: 'research',
      output: '【核心观点】政策环境支持风险偏好修复。',
      thinking: '形成阶段判断',
      thinking_stage: 'synthesis',
      thoughts: ['拆解议题', '读取政策 Skill', '形成阶段判断'],
      tools: ['tushare_query'],
      required_skills: ['policy-monitor'],
      registered_skills: ['policy-monitor'],
      used_skills: ['policy-monitor'],
      evidence: [],
      started_at: '2026-07-24T00:00:00Z',
      completed_at: '2026-07-24T00:00:30Z',
      error: null,
    },
  },
  plan: '',
  consensus: '',
  decision: '历史决议',
  orchestra_thinking: '',
  orchestra_thinking_stage: null,
  error: null,
  owner_id: 'local-user',
  portfolio_id: null,
  parent_run_id: null,
  revision: 1,
  revision_note: '',
  secret_refs: {},
};

vi.mock('@/hooks/useCommitteeRun', () => ({
  useCommitteeRun: () => ({
    agents: [agent],
    health: {
      status: 'ok',
      agents: 19,
      default_mode: 'demo',
      live_ready: true,
      model: 'gpt-5.5',
      data_tools: { tushare: true, a_stock: true, global_stock: true, tavily: true, ima: true },
    },
    overview: {
      version: '0.5.0',
      persistence: 'postgresql',
      database_path: 'postgresql://orchestra:***@db:5432/orchestra',
      schema_version: 3,
      queue_backend: 'redis-durable',
      secret_vault: { backend: 'environment', key_id: 'abc123def456' },
      max_concurrency: 3,
      run_history_limit: 50,
      runs: { total: 1, active: 0 },
      groups: { 宏观组: 3 },
      skills: { installed: 200, assigned: 1, missing: 0 },
      data: { tushare_endpoints: 1, tushare_ready: true, tavily_ready: true, llm_ready: true },
    },
    queueJobs: [],
    skillCatalog: [{
      name: 'policy-monitor',
      description: '政策监控',
      assigned_agents: ['MACRO-01'],
    }],
    currentUser: { id: 'local-user', name: '本地管理员', role: 'owner', created_at: snapshot.created_at },
    users: [{ id: 'local-user', name: '本地管理员', role: 'owner', created_at: snapshot.created_at }],
    portfolios: [],
    portfolioDetail: null,
    secrets: [],
    comparison: null,
    recentRuns: [{
      id: 'run-1',
      topic: '历史议题',
      mode: 'demo',
      status: 'completed',
      phase: 'completed',
      created_at: snapshot.created_at,
      updated_at: snapshot.updated_at,
      completed_agents: 19,
      total_agents: 19,
      error: null,
      owner_id: 'local-user',
      portfolio_id: null,
      parent_run_id: null,
      revision: 1,
      evidence_count: 0,
    }],
    snapshot,
    events: [],
    artifacts: [],
    runEvidence: [],
    loading: false,
    error: null,
    setError: vi.fn(),
    newRun: mocks.newRun,
    startRun: vi.fn(),
    cancelRun: vi.fn(),
    loadRun: mocks.loadRun,
    refreshSystemData: mocks.refreshSystemData,
    refreshProfiles: mocks.refreshProfiles,
    reconsiderRun: vi.fn(),
    compareRuns: vi.fn(),
    addPortfolio: vi.fn(),
    loadPortfolioDetail: vi.fn(),
    addPortfolioTransaction: vi.fn(),
    addPortfolioValuation: vi.fn(),
    addUser: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    addSecret: vi.fn(),
    removeSecret: vi.fn(),
  }),
}));

import OrchestraApp from '@/OrchestraApp';
import { runningStateLabel } from '@/utils/orchestraStatus';

describe('Orchestra sidebar navigation', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
    mocks.loadRun.mockReset();
    mocks.loadRun.mockResolvedValue(snapshot);
    mocks.newRun.mockReset();
    mocks.refreshSystemData.mockReset();
    mocks.refreshSystemData.mockResolvedValue({});
    mocks.refreshProfiles.mockReset();
    mocks.refreshProfiles.mockResolvedValue([agent]);
  });

  it('opens a workspace directly from the URL and follows browser navigation', async () => {
    window.history.replaceState({}, '', '/?workspace=reports');
    render(<OrchestraApp />);

    expect(screen.getByRole('complementary', { name: '研究成果' })).toBeTruthy();

    window.history.pushState({}, '', '/?workspace=data');
    window.dispatchEvent(new PopStateEvent('popstate'));
    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: '数据工具' })).toBeTruthy();
    });
  });

  it('keeps internal navigation synchronized with the workspace query', async () => {
    const user = userEvent.setup();
    render(<OrchestraApp />);

    await user.click(screen.getByRole('button', { name: '历史讨论' }));
    expect(new URL(window.location.href).searchParams.get('workspace')).toBe('history');
    await user.click(screen.getByRole('button', { name: '关闭侧边面板' }));
    expect(new URL(window.location.href).searchParams.get('workspace')).toBe('committee');
  });

  it('starts a clean task without deleting historical runs', async () => {
    const user = userEvent.setup();
    render(<OrchestraApp />);

    expect(screen.getByDisplayValue('历史议题')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '新建任务' }));

    expect(mocks.newRun).toHaveBeenCalledTimes(1);
    expect((screen.getByRole('textbox', { name: '投委会议题' }) as HTMLInputElement).value).toBe('');
    expect(screen.getByRole('button', { name: '历史讨论' })).toBeTruthy();
  });

  it('keeps the active status truthful while the chair is converging', () => {
    expect(runningStateLabel('planning', 0)).toBe('数据基座构建中');
    expect(runningStateLabel('research', 2)).toBe('2席研究中');
    expect(runningStateLabel('deliberation', 2)).toBe('2席审议中');
    expect(runningStateLabel('convergence', 0)).toBe('主席收敛中');
    expect(runningStateLabel('decision', 0)).toBe('主席决议中');
  });

  it('opens every sidebar workspace and supports agent drill-down', async () => {
    const user = userEvent.setup();
    render(<OrchestraApp />);

    const destinations = [
      ['投委会', '投委会控制台'],
      ['历史讨论', '历史讨论'],
      ['研究成果', '研究成果'],
      ['研究席位', '研究席位名册'],
      ['Skills', 'Skills 能力矩阵'],
      ['数据工具', '数据工具'],
      ['账户与组合', '账户与组合'],
      ['运行设置', '运行设置'],
    ];

    for (const [button, title] of destinations) {
      await user.click(screen.getByRole('button', { name: button }));
      expect(screen.getByRole('complementary', { name: title })).toBeTruthy();
    }

    await user.click(screen.getByRole('button', { name: '研究席位' }));
    const directory = screen.getByRole('complementary', { name: '研究席位名册' });
    await user.click(within(directory).getByRole('button', { name: /林雅横/ }));
    expect(screen.getByRole('complementary', { name: '林雅横 详情' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '关闭详情' }));
    await user.click(screen.getByRole('button', { name: '投委会' }));
    const committee = screen.getByRole('complementary', { name: '投委会控制台' });
    await user.click(within(committee).getByRole('button', { name: /林雅横/ }));
    expect(screen.getByText('政策环境支持风险偏好修复。')).toBeTruthy();
    expect(screen.getAllByText('policy-monitor')).toHaveLength(4);
  });

  it('loads historical runs and applies real display settings', async () => {
    const user = userEvent.setup();
    render(<OrchestraApp />);

    await user.click(screen.getByRole('button', { name: '投委会' }));
    await user.click(screen.getByRole('button', { name: /历史议题/ }));
    await waitFor(() => expect(mocks.loadRun).toHaveBeenCalledWith('run-1'));
    expect(screen.getByDisplayValue('历史议题')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '运行设置' }));
    expect(screen.getByText('PostgreSQL')).toBeTruthy();
    expect(screen.getByText('redis-durable')).toBeTruthy();
    expect(screen.getByText('environment · abc123def456')).toBeTruthy();
    const thinkingSwitch = screen.getByRole('switch', { name: /Agent 思考流/ });
    const artifactSwitch = screen.getByRole('switch', { name: /成果纵深栈/ });
    expect(thinkingSwitch.getAttribute('aria-checked')).toBe('true');
    expect(artifactSwitch.getAttribute('aria-checked')).toBe('true');
    await user.click(thinkingSwitch);
    await user.click(artifactSwitch);
    expect(thinkingSwitch.getAttribute('aria-checked')).toBe('false');
    expect(artifactSwitch.getAttribute('aria-checked')).toBe('false');
  });
});
