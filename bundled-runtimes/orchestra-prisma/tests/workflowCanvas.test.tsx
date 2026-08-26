// @vitest-environment jsdom

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import WorkflowCanvas from '@/components/orchestra/WorkflowCanvas';
import type { AgentProfile, AgentRuntime, DecisionEvent } from '@/types/orchestra';

const profile: AgentProfile = {
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

const runtime = (status: AgentRuntime['status']): AgentRuntime => ({
  id: profile.id,
  status,
  phase: 'research',
  output: status === 'completed' ? '【核心观点】政策环境支持风险偏好修复。' : '',
  thinking: '交叉核对政策方向、流动性和反证条件',
  thinking_stage: 'reasoning',
  thoughts: ['拆解议题', '载入政策监控框架', '形成阶段判断'],
  tools: status === 'completed' ? ['tushare_query'] : [],
  required_skills: ['policy-monitor', 'finance-data-router', 'data-quality-checker'],
  registered_skills: ['policy-monitor'],
  used_skills: status === 'completed' ? ['policy-monitor'] : [],
  evidence: [],
  started_at: '2026-07-23T00:00:00Z',
  completed_at: status === 'completed' ? '2026-07-23T00:00:01Z' : null,
  error: null,
});

const renderCanvas = (agentRuntime: AgentRuntime) => render(
  <WorkflowCanvas
    agents={[profile]}
    runtimes={{ [profile.id]: agentRuntime }}
    phase="research"
    topic="测试投决议题"
    plan="研究计划"
    consensus=""
    decision=""
    orchestraThinking=""
    showThinking
    showArtifacts
    onSelect={vi.fn()}
  />,
);

describe('WorkflowCanvas', () => {
  it('streams an auditable thinking summary next to a working agent', () => {
    renderCanvas(runtime('working'));

    expect(screen.getByText('THINKING STREAM')).toBeTruthy();
    expect(screen.getByText('交叉核对政策方向、流动性和反证条件')).toBeTruthy();
    expect(screen.getByText('群体 AI 智脑')).toBeTruthy();
  });

  it('stacks method, evidence and result artifacts after completion', () => {
    renderCanvas(runtime('completed'));

    expect(screen.getByText('研究路径')).toBeTruthy();
    expect(screen.getByText('数据证据')).toBeTruthy();
    expect(screen.getByText('阶段成果')).toBeTruthy();
    expect(screen.getByText('1/1')).toBeTruthy();
  });

  it('renders a dynamically added custom agent without a hard-coded coordinate', () => {
    const customProfile: AgentProfile = {
      ...profile,
      id: 'CUSTOM-A1B2C3D4',
      name: '半导体 林舟',
      group: '股票组',
      is_custom: true,
    };
    render(
      <WorkflowCanvas
        agents={[profile, customProfile]}
        runtimes={{ [profile.id]: runtime('working'), [customProfile.id]: { ...runtime('idle'), id: customProfile.id } }}
        phase="research"
        topic="测试动态扩席"
        plan="研究计划"
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: '半导体 林舟 详情' })).toBeTruthy();
    expect(screen.getByText('动态研究席位拓扑 · 2 席')).toBeTruthy();
  });

  it('supports agent focus mode, search location and group collapsing', async () => {
    const user = userEvent.setup();
    const secondProfile: AgentProfile = {
      ...profile,
      id: 'EQUITY-01',
      name: '科技成长 绍迪',
      group: '股票组',
    };
    const result = render(
      <WorkflowCanvas
        agents={[profile, secondProfile]}
        runtimes={{ [profile.id]: runtime('working'), [secondProfile.id]: { ...runtime('idle'), id: secondProfile.id } }}
        phase="research"
        topic="测试焦点模式"
        plan="研究计划"
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '聚焦 林雅横' }));
    expect(result.container.querySelectorAll('.workflow-agent-cluster.is-focused')).toHaveLength(1);
    expect(result.container.querySelectorAll('.workflow-agent-cluster.is-dimmed')).toHaveLength(1);
    expect(result.container.querySelectorAll('.workflow-links g.is-focused')).toHaveLength(2);

    await user.click(screen.getAllByRole('button', { name: '退出焦点模式' })[0]);
    await user.click(screen.getByRole('button', { name: '折叠股票组' }));
    expect(screen.getAllByRole('button', { name: '展开股票组' }).length).toBeGreaterThan(0);
    expect(result.container.querySelectorAll('.workflow-group-summary')).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: '搜索 Agent' }));
    await user.type(screen.getByRole('textbox', { name: '搜索画布 Agent' }), '绍迪');
    await user.click(screen.getByRole('button', { name: /EQUITY-01/ }));
    expect(result.container.querySelectorAll('.workflow-agent-cluster.is-focused')).toHaveLength(1);
    expect(screen.getAllByText('科技成长 绍迪').length).toBeGreaterThan(0);
  });

  it('renders scheduler telemetry and external execution source on active agents', () => {
    const externalProfile: AgentProfile = {
      ...profile,
      id: 'CUSTOM-A1B2C3D4',
      connection: { kind: 'external_http', endpoint: 'https://agent.example.com/run', timeout_seconds: 90 },
      is_custom: true,
    };
    const workingRuntime = {
      ...runtime('working'),
      id: externalProfile.id,
      started_at: new Date(Date.now() - 18_000).toISOString(),
      tools: ['external_agent'],
      evidence: [{
        id: 'evidence-1',
        source_name: '外部研究服务',
        source_url: null,
        observed_at: '2026-07-26',
        retrieved_at: '2026-07-26T00:00:00Z',
        tool_name: 'external_agent',
        interface_name: 'external_http',
        params: {},
        status: 'success',
        excerpt: '外部证据',
        content_hash: 'abc123',
      }],
    };
    const result = render(
      <WorkflowCanvas
        agents={[externalProfile]}
        runtimes={{ [externalProfile.id]: workingRuntime }}
        events={[{
          id: 'event-1',
          run_id: 'run-1',
          seq: 1,
          type: 'agent.tool.started',
          created_at: '2026-07-26T00:00:00Z',
          phase: 'research',
          agent_id: externalProfile.id,
          payload: { tool: 'external_agent' },
        }]}
        maxConcurrency={3}
        phase="research"
        topic="测试调度遥测"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Agent 调度状态').textContent).toContain('1/3');
    expect(result.container.querySelector('.workflow-agent-topline em.is-external_http')).toBeTruthy();
    expect(screen.getAllByText('external_agent').length).toBeGreaterThan(0);
    expect(result.container.querySelector('.workflow-agent-metrics .is-working')?.textContent).toContain('执行');
    fireEvent.scroll(result.container.querySelector('.workflow-scroll') as HTMLElement);
    expect(screen.getByRole('navigation', { name: '画布小地图' })).toBeTruthy();
  });

  it('exposes a real event replay timeline and returns to live state', async () => {
    const user = userEvent.setup();
    const onReplayEventIndexChange = vi.fn();
    const events: DecisionEvent[] = [{
      id: 'e1', run_id: 'run-1', seq: 1, type: 'run.started', created_at: '2026-07-26T00:00:00Z', phase: null, agent_id: null, payload: {},
    }, {
      id: 'e2', run_id: 'run-1', seq: 2, type: 'agent.started', created_at: '2026-07-26T00:00:01Z', phase: 'research', agent_id: profile.id, payload: {},
    }];
    const result = render(
      <WorkflowCanvas
        agents={[profile]}
        runtimes={{ [profile.id]: runtime('working') }}
        events={events}
        phase="research"
        topic="测试运行回放"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        replayEventIndex={null}
        onReplayEventIndexChange={onReplayEventIndexChange}
        onSelect={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '从头回放运行' }));
    expect(onReplayEventIndexChange).toHaveBeenCalledWith(0);

    result.rerender(
      <WorkflowCanvas
        agents={[profile]}
        runtimes={{ [profile.id]: runtime('working') }}
        events={events}
        phase="research"
        topic="测试运行回放"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        replayEventIndex={1}
        onReplayEventIndexChange={onReplayEventIndexChange}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole('slider', { name: '运行回放时间轴' })).toBeTruthy();
    expect(screen.getByText(/开始执行/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '返回实时状态' }));
    expect(onReplayEventIndexChange).toHaveBeenCalledWith(null);
  });

  it('visualizes manager stance and opens the attached report stack', async () => {
    const user = userEvent.setup();
    const manager = { ...profile, id: 'PM-01', name: 'PM-01 测试经理', group: '基金经理组' };
    const managerRuntime = {
      ...runtime('completed'),
      id: manager.id,
      phase: 'deliberation',
      output: '【置信度】中\n【投票】有条件赞成',
    };
    const onOpenReport = vi.fn();
    const result = render(
      <WorkflowCanvas
        agents={[manager]}
        runtimes={{ [manager.id]: managerRuntime }}
        phase="convergence"
        topic="测试投票分歧"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
        onOpenReport={onOpenReport}
      />,
    );

    expect(screen.getByLabelText('基金经理投票分布').textContent).toContain('谨慎 1');
    expect(result.container.querySelector('.workflow-links g.is-vote.is-cautious')).toBeTruthy();
    expect(screen.getByText('谨慎')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '打开 PM-01 测试经理 阶段成果' }));
    expect(onOpenReport).toHaveBeenCalledWith(manager);
  });

  it('virtualizes offscreen cards above 35 agents while retaining every minimap marker', async () => {
    const manyAgents = Array.from({ length: 60 }, (_, index) => ({
      ...profile,
      id: `MACRO-${String(index + 1).padStart(2, '0')}`,
      name: `宏观研究员 ${index + 1}`,
    }));
    const manyRuntimes = Object.fromEntries(manyAgents.map((agent) => [
      agent.id,
      { ...runtime('idle'), id: agent.id },
    ]));
    const result = render(
      <WorkflowCanvas
        agents={manyAgents}
        runtimes={manyRuntimes}
        phase="research"
        topic="50席以上画布性能测试"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
      />,
    );
    const scroll = result.container.querySelector('.workflow-scroll') as HTMLElement;
    Object.defineProperties(scroll, {
      clientWidth: { configurable: true, value: 720 },
      clientHeight: { configurable: true, value: 560 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(scroll);

    await waitFor(() => {
      expect(result.container.querySelectorAll('.workflow-agent')).not.toHaveLength(60);
    });
    expect(result.container.querySelectorAll('.workflow-agent').length).toBeGreaterThan(0);
    expect(result.container.querySelectorAll('.workflow-minimap circle')).toHaveLength(60);
    expect(screen.getByLabelText('Agent 调度状态').textContent).toContain('渲染');
  });

  it('uses multiple columns when a committee lane grows beyond seven agents', () => {
    const expandedAgents = Array.from({ length: 8 }, (_, index) => ({
      ...profile,
      id: `MACRO-${index + 1}`,
      name: `宏观席位 ${index + 1}`,
    }));
    const result = render(
      <WorkflowCanvas
        agents={expandedAgents}
        runtimes={Object.fromEntries(expandedAgents.map((agent) => [agent.id, { ...runtime('idle'), id: agent.id }]))}
        phase="research"
        topic="自适应多列布局"
        plan=""
        consensus=""
        decision=""
        orchestraThinking=""
        showThinking
        showArtifacts
        onSelect={vi.fn()}
      />,
    );

    const leftPositions = new Set(Array.from(result.container.querySelectorAll<HTMLElement>('.workflow-agent-cluster')).map((item) => item.style.left));
    expect(leftPositions.size).toBe(2);
  });

  it('switches layout modes and persists pinned agent positions', async () => {
    const user = userEvent.setup();
    const result = renderCanvas(runtime('completed'));

    await user.click(screen.getByRole('button', { name: '分组布局' }));
    expect(screen.getByRole('button', { name: '分组布局' }).classList.contains('is-active')).toBe(true);
    await user.click(screen.getByRole('button', { name: '固定 林雅横' }));
    expect(result.container.querySelector('.workflow-agent-cluster.is-pinned')).toBeTruthy();

    await waitFor(() => {
      const saved = JSON.parse(window.localStorage.getItem('orchestra:workflow-layout:v2') || '{}');
      expect(saved.mode).toBe('grouped');
      expect(saved.positions.grouped[profile.id]).toBeTruthy();
    });

    await user.click(screen.getByRole('button', { name: '重置当前布局' }));
    expect(result.container.querySelector('.workflow-agent-cluster.is-pinned')).toBeFalsy();
  });

  it('drags an agent in world coordinates and automatically pins the new position', async () => {
    const result = renderCanvas(runtime('completed'));
    const cluster = result.container.querySelector<HTMLElement>('.workflow-agent-cluster');
    const initialLeft = cluster?.style.left;

    fireEvent.pointerDown(screen.getByRole('button', { name: '拖动 林雅横' }), { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(window, { clientX: 150, clientY: 130 });
    fireEvent.pointerUp(window);

    await waitFor(() => expect(cluster?.classList.contains('is-pinned')).toBe(true));
    expect(cluster?.style.left).not.toBe(initialLeft);
  });
});
