import React from 'react';
import { AlertTriangle, Check, Clock3, Loader2 } from 'lucide-react';
import type { AgentProfile, AgentRuntime } from '@/types/orchestra';

const statusLabel = {
  idle: '待命',
  queued: '排队',
  working: '研究中',
  completed: '完成',
  failed: '异常',
};

const StatusIcon = ({ status }: { status: AgentRuntime['status'] }) => {
  if (status === 'working') return <Loader2 size={13} className="animate-spin" />;
  if (status === 'completed') return <Check size={13} strokeWidth={2.5} />;
  if (status === 'failed') return <AlertTriangle size={13} />;
  return <Clock3 size={13} />;
};

const AgentSeat = ({
  profile,
  runtime,
  onSelect,
}: {
  profile: AgentProfile;
  runtime?: AgentRuntime;
  onSelect: () => void;
}) => {
  const status = runtime?.status || 'idle';
  return (
    <button
      type="button"
      className={`orchestra-seat status-${status}`}
      onClick={onSelect}
      aria-label={`查看 ${profile.id} ${profile.name}`}
    >
      <span className="orchestra-seat-motion" aria-hidden="true" />
      <span className="orchestra-seat-head">
        <span className="orchestra-seat-id">{profile.id}</span>
        <span className={`orchestra-status status-${status}`}>
          <StatusIcon status={status} />
          {statusLabel[status]}
        </span>
      </span>
      <strong>{profile.name}</strong>
      <span className="orchestra-seat-focus">{profile.focus}</span>
      <span className="orchestra-skill-line">
        {profile.skills.slice(0, 2).join(' · ')}
        {profile.skills.length > 2 ? ` +${profile.skills.length - 2}` : ''}
      </span>
      {runtime?.output && <span className="orchestra-seat-output">{runtime.output}</span>}
    </button>
  );
};

export default AgentSeat;

