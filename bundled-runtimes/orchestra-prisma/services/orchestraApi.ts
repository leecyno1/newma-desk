import type {
  AgentProfile,
  DecisionEvent,
  ExecutionMode,
  HealthStatus,
  RunSnapshot,
  RunSummary,
  SkillCatalogItem,
  SystemOverview,
  ProfileUpdate,
  Portfolio,
  PortfolioDetail,
  PortfolioNavSnapshot,
  PortfolioTransaction,
  CreatePortfolioTransactionPayload,
  CreatePortfolioValuationPayload,
  CreateUserResponse,
  AuthSessionResponse,
  QueueJob,
  RunArtifact,
  RunEvidence,
  RunComparison,
  SecretMetadata,
  UserProfile,
  CreateAgentPayload,
  AgentInterventionAction,
  AgentInterventionResponse,
} from '@/types/orchestra';

const parseResponse = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail || `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
};

export const getHealth = async (): Promise<HealthStatus> => {
  return parseResponse<HealthStatus>(await fetch('/healthz'));
};

export const getAgents = async (): Promise<AgentProfile[]> => {
  return parseResponse<AgentProfile[]>(await fetch('/api/agents'));
};

export const getSkillCatalog = async (): Promise<SkillCatalogItem[]> => {
  return parseResponse<SkillCatalogItem[]>(await fetch('/api/skills'));
};

export const updateAgentProfile = async (
  agentId: string,
  updates: Partial<ProfileUpdate>,
): Promise<AgentProfile> => {
  return parseResponse<AgentProfile>(
    await fetch(`/api/agents/${agentId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    }),
  );
};

export const createAgentProfile = async (
  payload: CreateAgentPayload,
): Promise<AgentProfile> => {
  return parseResponse<AgentProfile>(await fetch('/api/agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const deleteAgentProfile = async (agentId: string): Promise<void> => {
  const response = await fetch(`/api/agents/${agentId}`, { method: 'DELETE' });
  if (!response.ok) await parseResponse(response);
};

export const getSystemOverview = async (): Promise<SystemOverview> => {
  return parseResponse<SystemOverview>(await fetch('/api/system/overview'));
};

export const getQueueJobs = async (limit = 30): Promise<QueueJob[]> => {
  return parseResponse<QueueJob[]>(await fetch(`/api/system/queue/jobs?limit=${limit}`));
};

export const getCurrentUser = async (): Promise<UserProfile> => {
  return parseResponse<UserProfile>(await fetch('/api/users/me'));
};

export const getUsers = async (): Promise<UserProfile[]> => {
  return parseResponse<UserProfile[]>(await fetch('/api/users'));
};

export const createUser = async (payload: {
  name: string;
  role: UserProfile['role'];
}): Promise<CreateUserResponse> => {
  return parseResponse<CreateUserResponse>(await fetch('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const createAuthSession = async (
  userId: string,
  apiToken: string,
): Promise<AuthSessionResponse> => {
  return parseResponse<AuthSessionResponse>(await fetch('/api/auth/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, api_token: apiToken }),
  }));
};

export const deleteAuthSession = async (): Promise<void> => {
  const response = await fetch('/api/auth/session', { method: 'DELETE' });
  if (!response.ok) await parseResponse(response);
};

export const getPortfolios = async (): Promise<Portfolio[]> => {
  return parseResponse<Portfolio[]>(await fetch('/api/portfolios'));
};

export const createPortfolio = async (payload: {
  name: string;
  description: string;
  base_currency: string;
}): Promise<Portfolio> => {
  return parseResponse<Portfolio>(await fetch('/api/portfolios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const getPortfolioDetail = async (portfolioId: string): Promise<PortfolioDetail> => {
  return parseResponse<PortfolioDetail>(await fetch(`/api/portfolios/${portfolioId}`));
};

export const createPortfolioTransaction = async (
  portfolioId: string,
  payload: CreatePortfolioTransactionPayload,
): Promise<PortfolioTransaction> => {
  return parseResponse<PortfolioTransaction>(await fetch(`/api/portfolios/${portfolioId}/transactions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const createPortfolioValuation = async (
  portfolioId: string,
  payload: CreatePortfolioValuationPayload,
): Promise<PortfolioNavSnapshot> => {
  return parseResponse<PortfolioNavSnapshot>(await fetch(`/api/portfolios/${portfolioId}/valuations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const getSecrets = async (): Promise<SecretMetadata[]> => {
  return parseResponse<SecretMetadata[]>(await fetch('/api/secrets'));
};

export const createSecret = async (payload: {
  provider: SecretMetadata['provider'];
  label: string;
  value: string;
}): Promise<SecretMetadata> => {
  return parseResponse<SecretMetadata>(await fetch('/api/secrets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }));
};

export const deleteSecret = async (secretId: string): Promise<void> => {
  const response = await fetch(`/api/secrets/${secretId}`, { method: 'DELETE' });
  if (!response.ok) await parseResponse(response);
};

export const getCommitteeRuns = async (limit = 20): Promise<RunSummary[]> => {
  return parseResponse<RunSummary[]>(await fetch(`/api/runs?limit=${limit}`));
};

export const createCommitteeRun = async (
  topic: string,
  mode: ExecutionMode,
  portfolioId?: string | null,
): Promise<{ run_id: string; status: string; mode: ExecutionMode }> => {
  return parseResponse(
    await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, mode, portfolio_id: portfolioId || null }),
    }),
  );
};

export const getRunArtifacts = async (runId: string): Promise<RunArtifact[]> => {
  return parseResponse<RunArtifact[]>(await fetch(`/api/runs/${runId}/artifacts`));
};

export const getRunEvidence = async (runId: string): Promise<RunEvidence[]> => {
  return parseResponse<RunEvidence[]>(await fetch(`/api/runs/${runId}/evidence`));
};

export const reconsiderCommitteeRun = async (
  runId: string,
  note: string,
  mode?: ExecutionMode,
): Promise<{ run_id: string; status: string; mode: ExecutionMode }> => {
  return parseResponse(await fetch(`/api/runs/${runId}/revisions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note, mode }),
  }));
};

export const startAgentIntervention = async (
  runId: string,
  agentId: string,
  action: AgentInterventionAction,
  instruction: string,
): Promise<AgentInterventionResponse> => {
  return parseResponse<AgentInterventionResponse>(
    await fetch(`/api/runs/${runId}/agents/${agentId}/interventions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, instruction }),
    }),
  );
};

export const compareCommitteeRuns = async (runIds: string[]): Promise<RunComparison> => {
  return parseResponse<RunComparison>(await fetch('/api/run-comparisons', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: runIds }),
  }));
};

export const runExportUrl = (runId: string, format: 'pdf' | 'docx') => (
  `/api/runs/${runId}/exports/${format}`
);

export const getCommitteeRun = async (runId: string): Promise<RunSnapshot> => {
  return parseResponse<RunSnapshot>(await fetch(`/api/runs/${runId}`));
};

export const getCommitteeRunEvents = async (
  runId: string,
  limit = 600,
): Promise<DecisionEvent[]> => {
  return parseResponse<DecisionEvent[]>(
    await fetch(`/api/runs/${runId}/event-log?limit=${limit}`),
  );
};

export const getCommitteeRunReplayEvents = async (
  runId: string,
): Promise<DecisionEvent[]> => {
  return parseResponse<DecisionEvent[]>(
    await fetch(`/api/runs/${runId}/replay-log`),
  );
};

export const cancelCommitteeRun = async (runId: string): Promise<void> => {
  await parseResponse(await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' }));
};
