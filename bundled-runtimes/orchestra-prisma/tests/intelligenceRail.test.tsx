// @vitest-environment jsdom

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import IntelligenceRail from '@/components/orchestra/IntelligenceRail';
import type { AgentProfile, DecisionEvent, HealthStatus, RunSnapshot } from '@/types/orchestra';

const agent: AgentProfile = {
  id: 'ALLOC-03',
  name: '量化 陈静竹',
  title: '量化 陈静竹',
  group: '配置组',
  focus: '行业拥挤度',
  persona: '量化配置研究员',
  style: '先定义样本和窗口',
  default_prompt: '',
  shared_skills: [],
  specialty_skills: ['backtest-expert', 'sector-analyst', 'gf-dma-health-index'],
  skills: ['backtest-expert', 'sector-analyst', 'gf-dma-health-index'],
  available_skills: ['backtest-expert', 'sector-analyst', 'gf-dma-health-index'],
  missing_skills: [],
  research_channels: ['Tushare Pro', 'IMA Knowledge Base'],
  tushare_endpoints: ['daily_basic'],
  outputs: ['拥挤度诊断'],
};

const health: HealthStatus = {
  status: 'ok',
  agents: 19,
  default_mode: 'live',
  live_ready: true,
  model: 'gpt-5.5',
  data_tools: { tushare: true, a_stock: true, global_stock: true, tavily: true, ima: true },
};

const snapshot = {
  status: 'running',
} as RunSnapshot;

const event = (seq: number, type: string, payload: Record<string, unknown>): DecisionEvent => ({
  id: `event-${seq}`,
  run_id: 'run-1',
  seq,
  type,
  created_at: `2026-07-24T00:00:0${seq}Z`,
  phase: 'research',
  agent_id: 'ALLOC-03',
  payload,
});

describe('IntelligenceRail', () => {
  it('renders auditable skill, tool, evidence and draft events as a waterfall', () => {
    render(
      <IntelligenceRail
        agents={[agent]}
        health={health}
        snapshot={snapshot}
        events={[
          event(1, 'agent.skill.used', { skill: 'backtest-expert', source: 'orchestrator-preload' }),
          event(2, 'agent.tool.input', { tool: 'a_stock_data', params: { action: 'margin', symbol: '300308' } }),
          event(3, 'agent.evidence.recorded', {
            source_name: 'A Stock Data',
            interface_name: 'margin',
            observed_at: '2026-07-23',
            excerpt: '{"row_count":3}',
          }),
          event(4, 'agent.output.delta', { delta: '【拥挤度诊断】融资余额仍在高位，短期交易拥挤。' }),
        ]}
      />,
    );

    expect(screen.getByText('可审计执行瀑布')).toBeTruthy();
    expect(screen.getByText('量化 陈静竹 · Skill 激活')).toBeTruthy();
    expect(screen.getByText(/a_stock_data/)).toBeTruthy();
    expect(screen.getByText('量化 陈静竹 · 证据入库')).toBeTruthy();
    expect(screen.getByText(/融资余额仍在高位/)).toBeTruthy();
    expect(screen.getByText('IMA')).toBeTruthy();
  });
});
