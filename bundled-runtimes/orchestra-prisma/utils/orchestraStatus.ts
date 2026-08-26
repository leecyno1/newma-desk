export const runningStateLabel = (phase: string | undefined, working: number) => {
  if (phase === 'queued') return '任务排队中';
  if (phase === 'planning') return '数据基座构建中';
  if (phase === 'research') return working > 0 ? `${working}席研究中` : '研究编排中';
  if (phase === 'deliberation') return working > 0 ? `${working}席审议中` : '审议编排中';
  if (phase === 'convergence') return '主席收敛中';
  if (phase === 'decision') return '主席决议中';
  return working > 0 ? `${working}席执行中` : '任务推进中';
};
