// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import AgentCreateDialog from '@/components/orchestra/AgentCreateDialog';

const skills = [
  { name: 'finance-data-router', description: '金融数据路由', assigned_agents: [] },
  { name: 'data-quality-checker', description: '数据质量检查', assigned_agents: [] },
  { name: 'buy-side-equity-research-memo', description: '买方研究框架', assigned_agents: [] },
  { name: 'institutional-flow-tracker', description: '机构资金追踪', assigned_agents: [] },
];

describe('AgentCreateDialog', () => {
  it('creates a custom external agent with three selected skills and an isolated secret', async () => {
    const user = userEvent.setup();
    const created = {
      id: 'CUSTOM-A1B2C3D4',
      name: '半导体 林舟',
      title: '半导体产业研究员',
      group: '股票组',
      focus: '存储与先进封装',
      persona: '产业链研究员',
      style: '景气、供需与估值交叉验证',
      default_prompt: '',
      shared_skills: [],
      specialty_skills: skills.slice(0, 3).map((item) => item.name),
      skills: skills.slice(0, 3).map((item) => item.name),
      available_skills: skills.slice(0, 3).map((item) => item.name),
      missing_skills: [],
      research_channels: [],
      tushare_endpoints: [],
      outputs: [],
      is_custom: true,
      connection: { kind: 'external_http' as const, endpoint: 'https://agent.example.com/run', model: null, secret_id: 'secret-agent', timeout_seconds: 180 },
    };
    const onCreate = vi.fn().mockResolvedValue(created);
    const onCreated = vi.fn();
    render(
      <AgentCreateDialog
        skillCatalog={skills}
        secrets={[{ id: 'secret-agent', owner_id: 'local-user', provider: 'agent', label: '外部研究服务', created_at: '', updated_at: '' }]}
        onCreate={onCreate}
        onCreated={onCreated}
        onClose={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText('显示名称'), '半导体 林舟');
    await user.type(screen.getByLabelText('角色标题'), '半导体产业研究员');
    await user.type(screen.getByLabelText('研究边界'), '存储与先进封装');
    await user.type(screen.getByLabelText('角色定位'), '产业链研究员');
    await user.type(screen.getByLabelText('报告风格'), '景气、供需与估值交叉验证');
    for (const skill of skills.slice(0, 3)) await user.click(screen.getByRole('button', { name: `添加 ${skill.name}` }));
    await user.click(screen.getByRole('button', { name: '外部 Agent' }));
    await user.type(screen.getByLabelText('Endpoint'), 'https://agent.example.com/run');
    await user.selectOptions(screen.getByLabelText(/隔离密钥/), 'secret-agent');
    await user.click(screen.getByRole('button', { name: '创建 Agent' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      group: '股票组',
      skills: skills.slice(0, 3).map((item) => item.name),
      connection: expect.objectContaining({
        kind: 'external_http',
        endpoint: 'https://agent.example.com/run',
        secret_id: 'secret-agent',
      }),
    }));
    expect(onCreated).toHaveBeenCalledWith(created);
  });
});
