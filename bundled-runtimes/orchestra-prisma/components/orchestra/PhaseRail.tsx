import React from 'react';
import { Check, Circle, Loader2 } from 'lucide-react';

const phases = [
  { id: 'planning', label: '议题拆解' },
  { id: 'research', label: '独立研究' },
  { id: 'deliberation', label: '经理审议' },
  { id: 'convergence', label: '分歧收敛' },
  { id: 'decision', label: '主席决议' },
];

const getPhaseIndex = (phase: string) => {
  if (phase === 'completed') return phases.length;
  return phases.findIndex((item) => item.id === phase);
};

const PhaseRail = ({ phase }: { phase: string }) => {
  const currentIndex = getPhaseIndex(phase);
  return (
    <div className="orchestra-phase-rail" aria-label="投委会流程">
      {phases.map((item, index) => {
        const isComplete = currentIndex > index;
        const isActive = currentIndex === index;
        return (
          <React.Fragment key={item.id}>
            <div
              className={`orchestra-phase ${isComplete ? 'is-complete' : ''} ${isActive ? 'is-active' : ''}`}
            >
              <span className="orchestra-phase-icon">
                {isComplete ? (
                  <Check size={13} strokeWidth={2.5} />
                ) : isActive ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Circle size={10} />
                )}
              </span>
              <span>{item.label}</span>
            </div>
            {index < phases.length - 1 && (
              <span className={`orchestra-phase-line ${currentIndex > index ? 'is-complete' : ''}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};

export default PhaseRail;

