import React from 'react';

const stages = [
  { id: 'planning', label: '议题拆解' },
  { id: 'research', label: '独立研究' },
  { id: 'deliberation', label: '经理审议' },
  { id: 'convergence', label: '分歧收敛' },
  { id: 'decision', label: '主席决议' },
];

const phaseOrder: Record<string, number> = {
  queued: -1,
  planning: 0,
  research: 1,
  deliberation: 2,
  convergence: 3,
  decision: 4,
  completed: 5,
  failed: 5,
  cancelled: 5,
};

const StageTimeline = ({ phase }: { phase: string }) => {
  const current = phaseOrder[phase] ?? -1;
  return (
    <footer className="stage-timeline">
      {stages.map((stage, index) => (
        <div
          key={stage.id}
          className={`${index === current ? 'is-active' : ''} ${index < current ? 'is-complete' : ''}`}
        >
          <i>{String(index + 1).padStart(2, '0')}</i>
          <span>{stage.label}</span>
        </div>
      ))}
    </footer>
  );
};

export default StageTimeline;
