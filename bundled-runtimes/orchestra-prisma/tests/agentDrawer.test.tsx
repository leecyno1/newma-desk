// @vitest-environment jsdom

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import AgentDrawer from '@/components/orchestra/AgentDrawer';
import type { AgentProfile, AgentRuntime, SkillCatalogItem } from '@/types/orchestra';

const profile: AgentProfile = {
  id: 'MACRO-01',
  name: '政策 林雅横',
  title: '政策研究员',
  group: '宏观组',
  focus: '政策方向与流动性',
  persona: '审慎、重视一手来源',
  style: '政策框架与情景推演',
  default_prompt: '优先核验官方政策原文。',
  shared_skills: ['finance-data-router', 'data-quality-checker'],
  specialty_skills: ['policy-monitor'],
  skills: ['policy-monitor', 'finance-data-router'],
  available_skills: ['policy-monitor', 'finance-data-router'],
  missing_skills: [],
  research_channels: ['Tushare', '官方政策网站'],
  tushare_endpoints: ['cn_m'],
  outputs: ['政策判断'],
};

const runtime: AgentRuntime = {
  id: profile.id,
  status: 'completed',
  phase: 'research',
  output: '【核心观点】政策环境边际改善。\n【反证条件】流动性重新收紧。',
  thinking: '形成阶段判断',
  thinking_stage: 'synthesis',
  thoughts: ['拆解议题', '核验政策原文', '形成阶段判断'],
  tools: ['tushare_query'],
  required_skills: ['policy-monitor'],
  registered_skills: ['policy-monitor', 'finance-data-router'],
  used_skills: ['policy-monitor'],
  evidence: [],
  started_at: '2026-07-24T00:00:00Z',
  completed_at: '2026-07-24T00:01:00Z',
  error: null,
};

const skillCatalog: SkillCatalogItem[] = [
  { name: 'policy-monitor', description: '政策监控', assigned_agents: ['MACRO-01'] },
  { name: 'finance-data-router', description: '金融数据路由', assigned_agents: ['MACRO-01'] },
  { name: 'data-quality-checker', description: '数据质量检查', assigned_agents: [] },
];

describe('AgentDrawer', () => {
  it('shows the full stage report and separates skill audit states', () => {
    render(
      <AgentDrawer
        profile={profile}
        runtime={runtime}
        skillCatalog={skillCatalog}
        onSave={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('阶段成果报告')).toBeTruthy();
    expect(screen.getByText(/政策环境边际改善/)).toBeTruthy();
    expect(screen.getByText('必选')).toBeTruthy();
    expect(screen.getByText('已注册')).toBeTruthy();
    expect(screen.getByText('实际读取')).toBeTruthy();
  });

  it('edits identity, default prompt and installed skills', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue({ ...profile, name: '政策 新名称' });
    render(
      <AgentDrawer
        profile={profile}
        runtime={runtime}
        skillCatalog={skillCatalog}
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '编辑 Profile' }));
    const nameInput = screen.getByLabelText('显示名称');
    await user.clear(nameInput);
    await user.type(nameInput, '政策 新名称');
    const promptInput = screen.getByLabelText('自定义默认提示词');
    await user.clear(promptInput);
    await user.type(promptInput, '只采用可追溯的一手来源。');
    await user.type(screen.getByPlaceholderText('搜索已安装 Skills'), 'data-quality');
    await user.click(screen.getByRole('button', { name: /data-quality-checker/ }));
    await user.click(screen.getByRole('button', { name: '保存 Profile' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(
      'MACRO-01',
      expect.objectContaining({
        name: '政策 新名称',
        default_prompt: '只采用可追溯的一手来源。',
        skills: ['policy-monitor', 'finance-data-router', 'data-quality-checker'],
      }),
    );
  });

  it('configures an independent model and deletes only a custom agent after confirmation', async () => {
    const user = userEvent.setup();
    const customProfile: AgentProfile = {
      ...profile,
      id: 'CUSTOM-A1B2C3D4',
      is_custom: true,
      skills: ['policy-monitor', 'finance-data-router', 'data-quality-checker'],
      connection: { kind: 'orchestra', timeout_seconds: 180 },
    };
    const onSave = vi.fn().mockResolvedValue(customProfile);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    render(
      <AgentDrawer
        profile={customProfile}
        runtime={runtime}
        skillCatalog={skillCatalog}
        secrets={[{ id: 'secret-openai', owner_id: 'local-user', provider: 'openai', label: '独立模型 Key', created_at: '', updated_at: '' }]}
        onSave={onSave}
        onDelete={onDelete}
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '编辑 Profile' }));
    await user.click(screen.getByRole('button', { name: '独立模型' }));
    await user.type(screen.getByLabelText('Endpoint'), 'https://llm.example.com/v1');
    await user.type(screen.getByLabelText('模型名称'), 'research-pro');
    await user.selectOptions(screen.getByLabelText('隔离密钥'), 'secret-openai');
    await user.click(screen.getByRole('button', { name: '保存 Profile' }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(
      customProfile.id,
      expect.objectContaining({
        connection: expect.objectContaining({ kind: 'openai_compatible', model: 'research-pro', secret_id: 'secret-openai' }),
      }),
    ));

    await user.click(screen.getByRole('button', { name: '编辑 Profile' }));
    await user.click(screen.getByRole('button', { name: '删除' }));
    await user.click(screen.getByRole('button', { name: '确认删除' }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(customProfile.id));
  });

  it('starts a targeted supplementary-data intervention for a completed agent', async () => {
    const user = userEvent.setup();
    const onIntervene = vi.fn().mockResolvedValue({ status: 'queued' });
    render(
      <AgentDrawer
        profile={profile}
        runtime={runtime}
        skillCatalog={skillCatalog}
        onSave={vi.fn()}
        onIntervene={onIntervene}
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: '补充数据' }));
    await user.type(screen.getByRole('textbox', { name: '干预指令' }), '补充近三个月政策与流动性数据');
    await user.click(screen.getByRole('button', { name: '发起干预' }));

    await waitFor(() => expect(onIntervene).toHaveBeenCalledWith(
      profile.id,
      'supplement',
      '补充近三个月政策与流动性数据',
    ));
  });
});
