export type ExecutionMode = 'demo' | 'live';
export type AgentStatus = 'idle' | 'queued' | 'working' | 'completed' | 'failed';
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type AgentInterventionAction = 'follow_up' | 'supplement' | 'rereview';

export type AgentConnectionKind = 'orchestra' | 'external_http' | 'openai_compatible';

export type AgentConnection = {
  kind: AgentConnectionKind;
  endpoint?: string | null;
  model?: string | null;
  secret_id?: string | null;
  timeout_seconds: number;
};

export type AgentProfile = {
  id: string;
  name: string;
  title: string;
  group: string;
  focus: string;
  persona: string;
  style: string;
  default_prompt: string;
  shared_skills: string[];
  specialty_skills: string[];
  skills: string[];
  available_skills: string[];
  missing_skills: string[];
  research_channels: string[];
  tushare_endpoints: string[];
  outputs: string[];
  connection?: AgentConnection;
  is_custom?: boolean;
};

export type AgentRuntime = {
  id: string;
  status: AgentStatus;
  phase: string | null;
  output: string;
  thinking: string;
  thinking_stage: string | null;
  thoughts: string[];
  tools: string[];
  required_skills: string[];
  registered_skills: string[];
  used_skills: string[];
  evidence: EvidenceRecord[];
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  intervention_id?: string | null;
  intervention_action?: AgentInterventionAction | null;
};

export type EvidenceRecord = {
  id: string;
  source_name: string;
  source_url: string | null;
  observed_at: string | null;
  retrieved_at: string;
  tool_name: string;
  interface_name: string | null;
  params: Record<string, unknown>;
  status: string;
  excerpt: string;
  content_hash: string;
};

export type SkillCatalogItem = {
  name: string;
  description: string;
  assigned_agents: string[];
};

export type ProfileUpdate = Pick<
  AgentProfile,
  'name' | 'title' | 'focus' | 'persona' | 'style' | 'default_prompt' | 'skills'
> & { connection?: AgentConnection };

export type CreateAgentPayload = {
  name: string;
  title: string;
  group: '宏观组' | '配置组' | '股票组' | '基金经理组';
  focus: string;
  persona: string;
  style: string;
  default_prompt: string;
  skills: string[];
  connection: AgentConnection;
};

export type RunSnapshot = {
  id: string;
  topic: string;
  mode: ExecutionMode;
  status: RunStatus;
  phase: string;
  created_at: string;
  updated_at: string;
  last_event_seq: number;
  agents: Record<string, AgentRuntime>;
  plan: string;
  consensus: string;
  decision: string;
  orchestra_thinking: string;
  orchestra_thinking_stage: string | null;
  error: string | null;
  owner_id: string;
  portfolio_id: string | null;
  parent_run_id: string | null;
  revision: number;
  revision_note: string;
  secret_refs: Record<string, string>;
};

export type RunSummary = {
  id: string;
  topic: string;
  mode: ExecutionMode;
  status: RunStatus;
  phase: string;
  created_at: string;
  updated_at: string;
  completed_agents: number;
  total_agents: number;
  error: string | null;
  owner_id: string;
  portfolio_id: string | null;
  parent_run_id: string | null;
  revision: number;
  evidence_count: number;
};

export type SystemOverview = {
  version: string;
  persistence: 'memory' | string;
  database_path?: string;
  schema_version?: number;
  queue_backend?: string;
  queue?: QueueStatus;
  redis_configured?: boolean;
  secret_vault?: {
    backend: 'file' | 'environment' | string;
    key_id: string;
  } | null;
  max_concurrency: number;
  run_history_limit: number;
  runs: { total: number; active: number };
  groups: Record<string, number>;
  skills: { installed: number; assigned: number; missing: number };
  data: {
    tushare_endpoints: number;
    tushare_ready: boolean;
    a_stock_ready: boolean;
    global_stock_ready: boolean;
    tavily_ready: boolean;
    ima_ready: boolean;
    llm_ready: boolean;
  };
};

export type QueueStatus = {
  backend: string;
  total: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  oldest_queued_at: string | null;
  max_attempts_seen: number;
  workers: number;
  lease_seconds: number;
  max_attempts: number;
  fallback_reason: string | null;
};

export type QueueJob = {
  run_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  attempts: number;
  available_at: string;
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_error: string | null;
  updated_at: string;
};

export type UserProfile = {
  id: string;
  name: string;
  role: 'owner' | 'manager' | 'researcher' | 'viewer';
  created_at: string;
};

export type Portfolio = {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  base_currency: string;
  created_at: string;
  updated_at: string;
};

export type PortfolioTransactionType = 'buy' | 'sell' | 'cash_in' | 'cash_out' | 'dividend' | 'interest' | 'fee';
export type PortfolioAssetClass = 'equity' | 'bond' | 'fund' | 'commodity' | 'future' | 'option' | 'cash' | 'other';

export type PortfolioTransaction = {
  id: string;
  portfolio_id: string;
  trade_date: string;
  transaction_type: PortfolioTransactionType;
  asset_code: string;
  asset_name: string;
  asset_class: PortfolioAssetClass;
  quantity: string;
  price: string;
  amount: string;
  fees: string;
  currency: string;
  notes: string;
  created_at: string;
};

export type PortfolioPosition = {
  asset_code: string;
  asset_name: string;
  asset_class: PortfolioAssetClass;
  currency: string;
  quantity: string;
  average_cost: string;
  last_price: string;
  market_value: string;
  cost_value: string;
  unrealized_pnl: string;
  realized_pnl: string;
};

export type PortfolioSummary = {
  as_of: string;
  currency: string;
  cash_balance: string;
  market_value: string;
  net_asset_value: string;
  total_cost: string;
  gross_exposure: string;
  unrealized_pnl: string;
  realized_pnl: string;
  income: string;
  fees: string;
  position_count: number;
};

export type PortfolioNavSnapshot = {
  id: string;
  portfolio_id: string;
  as_of: string;
  cash_balance: string;
  market_value: string;
  net_asset_value: string;
  unit_count: string | null;
  unit_nav: string | null;
  total_cost: string;
  unrealized_pnl: string;
  realized_pnl: string;
  note: string;
  created_at: string;
};

export type PortfolioDetail = {
  portfolio: Portfolio;
  summary: PortfolioSummary;
  positions: PortfolioPosition[];
  transactions: PortfolioTransaction[];
  nav_history: PortfolioNavSnapshot[];
};

export type CreatePortfolioTransactionPayload = {
  trade_date: string;
  transaction_type: PortfolioTransactionType;
  asset_code?: string;
  asset_name?: string;
  asset_class?: PortfolioAssetClass;
  quantity?: string;
  price?: string;
  amount?: string;
  fees?: string;
  currency: string;
  notes?: string;
};

export type CreatePortfolioValuationPayload = {
  as_of: string;
  marks: Array<{ asset_code: string; price: string; source: string }>;
  unit_count?: string | null;
  note?: string;
};

export type CreateUserResponse = {
  user: UserProfile;
  api_token: string;
};

export type AuthSessionResponse = {
  user: UserProfile;
  expires_at: string;
};

export type SecretMetadata = {
  id: string;
  owner_id: string;
  provider: 'openai' | 'tushare' | 'tavily' | 'ima' | 'agent';
  label: string;
  created_at: string;
  updated_at: string;
};

export type RunArtifact = {
  id: string;
  run_id: string;
  agent_id: string | null;
  kind: string;
  title: string;
  content: string;
  version: number;
  created_at: string;
};

export type AgentInterventionResponse = {
  intervention_id: string;
  run_id: string;
  agent_id: string;
  action: AgentInterventionAction;
  status: 'queued';
};

export type RunEvidence = EvidenceRecord & {
  run_id?: string;
  agent_id: string | null;
};

export type RunComparison = {
  runs: Array<{
    id: string;
    topic: string;
    revision: number;
    status: RunStatus;
    updated_at: string;
    decision: string;
  }>;
  comparisons: Array<{
    base_run_id: string;
    target_run_id: string;
    decision_diff: string[];
    consensus_changed: boolean;
    evidence_delta: number;
  }>;
};

export type DecisionEvent = {
  id: string;
  run_id: string;
  seq: number;
  type: string;
  created_at: string;
  phase: string | null;
  agent_id: string | null;
  payload: Record<string, unknown>;
};

export type HealthStatus = {
  status: string;
  agents: number;
  default_mode: ExecutionMode;
  live_ready: boolean;
  model: string | null;
  data_tools: {
    tushare: boolean;
    a_stock: boolean;
    global_stock: boolean;
    tavily: boolean;
    ima: boolean;
  };
};
