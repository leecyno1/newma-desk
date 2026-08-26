import { describe, expect, it } from 'vitest';
import type { AgentProfile, DecisionEvent } from '@/types/orchestra';
import {
  buildReplayFrames,
  extractReportSignal,
  replayRunAt,
  stanceHistoryFor,
} from '@/utils/orchestraReplay';

const agent = {
  id: 'PM-01', name: 'PM-01 测试经理', title: '基金经理', group: '基金经理组', focus: '组合审议', persona: '', style: '', default_prompt: '',
  shared_skills: [], specialty_skills: [], skills: ['council'], available_skills: ['council'], missing_skills: [], research_channels: [], tushare_endpoints: [], outputs: [],
} satisfies AgentProfile;

const event = (seq: number, type: string, payload: Record<string, unknown> = {}): DecisionEvent => ({
  id: `e${seq}`,
  run_id: 'run-1',
  seq,
  type,
  created_at: `2026-07-26T00:00:0${Math.min(seq, 9)}Z`,
  phase: type.startsWith('run.') ? null : 'deliberation',
  agent_id: type.startsWith('agent.') ? agent.id : null,
  payload,
});

describe('orchestra replay projection', () => {
  it('reconstructs agent status and output at an exact event boundary', () => {
    const events = [
      event(1, 'run.started'),
      event(2, 'phase.started', { label: '经理审议' }),
      event(3, 'agent.queued'),
      event(4, 'agent.started'),
      event(5, 'agent.output.delta', { delta: '【投票】有条件' }),
      event(6, 'agent.output.delta', { delta: '赞成' }),
      event(7, 'agent.completed', { output: '【置信度】中\n【投票】有条件赞成' }),
    ];

    const working = replayRunAt([agent], events, 4);
    expect(working.phase).toBe('deliberation');
    expect(working.runtimes[agent.id].status).toBe('working');
    expect(working.runtimes[agent.id].output).toBe('【投票】有条件');

    const completed = replayRunAt([agent], events, 6);
    expect(completed.runtimes[agent.id].status).toBe('completed');
    expect(extractReportSignal(completed.runtimes[agent.id].output).stance).toBe('cautious');
  });

  it('builds compact replay frames while preserving key events', () => {
    const events = [event(1, 'run.started')];
    for (let index = 2; index <= 70; index += 1) events.push(event(index, 'agent.output.delta', { delta: 'x' }));
    events.push(event(71, 'agent.completed', { output: '完成' }));

    const frames = buildReplayFrames(events);
    expect(frames.length).toBeLessThan(events.length);
    expect(frames[0].type).toBe('run.started');
    expect(frames.at(-1)?.type).toBe('agent.completed');
    expect(frames.filter((frame) => frame.isKey).length).toBe(2);
  });

  it('prefers structured votes and records real stance changes', () => {
    const events = [
      event(1, 'agent.vote.recorded', { stance: 'bullish', vote: '赞成' }),
      event(2, 'agent.vote.recorded', { stance: 'bearish', vote: '反对' }),
    ];

    expect(stanceHistoryFor(events, agent.id)).toEqual([
      { seq: 1, stance: 'bullish' },
      { seq: 2, stance: 'bearish' },
    ]);
  });

  it('clears stale agent state when a persisted run starts a new attempt', () => {
    const events = [
      event(1, 'run.started'),
      event(2, 'agent.started'),
      event(3, 'agent.completed', { output: '旧尝试成果' }),
      event(4, 'run.started'),
      event(5, 'phase.started', { label: '议题拆解' }),
    ];

    const replayed = replayRunAt([agent], events, events.length - 1);
    expect(replayed.runtimes[agent.id].status).toBe('idle');
    expect(replayed.runtimes[agent.id].output).toBe('');
  });

  it('detects a recovered attempt when a failed log is missing its restart event', () => {
    const recoveryEvent = {
      ...event(7, 'data.thinking', { summary: '恢复数据基座' }),
      phase: 'planning',
      agent_id: null,
    };
    const events = [
      event(1, 'run.started'),
      event(2, 'phase.started', { label: '经理审议' }),
      event(3, 'agent.started'),
      event(4, 'agent.vote.recorded', { stance: 'cautious', vote: '有条件赞成' }),
      event(5, 'agent.failed', { error: '磁盘写入失败' }),
      event(6, 'run.failed', { error: '磁盘写入失败' }),
      recoveryEvent,
    ];

    const replayed = replayRunAt([agent], events, events.length - 1);
    expect(replayed.status).toBe('running');
    expect(replayed.phase).toBe('planning');
    expect(replayed.runtimes[agent.id].status).toBe('idle');
    expect(buildReplayFrames(events).at(-1)).toMatchObject({ label: '恢复执行', isKey: true });
    expect(stanceHistoryFor(events, agent.id)).toEqual([]);
  });

  it('replays a human intervention as a new attached agent execution', () => {
    const intervention = (seq: number, type: string, payload: Record<string, unknown> = {}) => ({
      ...event(seq, type, payload),
      phase: 'intervention',
    });
    const events = [
      event(1, 'run.started'),
      event(2, 'agent.started'),
      event(3, 'agent.completed', { output: '【投票】赞成' }),
      event(4, 'run.completed'),
      intervention(5, 'agent.intervention.requested', { intervention_id: 'i-1', action: 'rereview' }),
      intervention(6, 'agent.intervention.started', { intervention_id: 'i-1', action: 'rereview', required_skills: ['council'] }),
      intervention(7, 'agent.output.delta', { delta: '【投票】反对' }),
      intervention(8, 'agent.intervention.completed', { output: '【置信度】高\n【投票】反对' }),
    ];

    const replayed = replayRunAt([agent], events, events.length - 1);
    expect(replayed.status).toBe('completed');
    expect(replayed.runtimes[agent.id]).toMatchObject({
      status: 'completed',
      phase: 'intervention',
      intervention_action: 'rereview',
      output: '【置信度】高\n【投票】反对',
    });
    expect(buildReplayFrames(events).at(-1)).toMatchObject({
      type: 'agent.intervention.completed',
      label: '增量报告已沉淀',
      isKey: true,
    });
    expect(stanceHistoryFor(events, agent.id).at(-1)?.stance).toBe('bearish');
  });
});
