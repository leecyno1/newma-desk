import React from 'react';
import { FileCheck2, Scale } from 'lucide-react';

const DecisionPanel = ({ consensus, decision }: { consensus: string; decision: string }) => {
  if (!consensus && !decision) return null;
  return (
    <section className="orchestra-decision-band">
      <div>
        <h2>
          <Scale size={17} /> 共识与分歧
        </h2>
        <pre>{consensus || '等待分歧收敛。'}</pre>
      </div>
      <div>
        <h2>
          <FileCheck2 size={17} /> 投委会决议
        </h2>
        <pre>{decision || '等待主席形成决议。'}</pre>
      </div>
    </section>
  );
};

export default DecisionPanel;

