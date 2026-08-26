import assert from 'node:assert/strict';
import { INITIAL } from '../editor/initial';
import { makeDraft } from '../editor/store';
import {
  loadAgentRuntimeSidecar,
  resetAgentRuntimeStoreMemory,
} from '../persist/agentRuntimeStore';
import { loadExternalProposal } from '../persist/externalProposalStore';
import { docFromTimeline } from '../persist/projectStore';
import type { AgentContext } from './context';
import {
  ExternalBridgeRuntime,
  type ExternalBridgeBinding,
} from './external-bridge-runtime';
import { revisionOf } from './external-edit-session';
import { stopAgentRunLeases } from './runtime-ledger';
import { loadRecoveredAgentSession } from './useAgentPersistence';

const projectId = `external-approval-hydration-${crypto.randomUUID()}`;
const base = docFromTimeline({ ...INITIAL, items: [] });
const live = makeDraft(base);
resetAgentRuntimeStoreMemory();

const context = (): AgentContext => ({
  commands: live.commands,
  getState: live.getState,
  getDoc: live.getDoc,
  getCreativeMode: () => null,
  templates: [],
  audio: [],
  getProjectId: () => projectId,
});

const binding = (editorInstanceId: string): ExternalBridgeBinding => ({
  projectId,
  editorInstanceId,
  baseRevision: revisionOf(live.getDoc()),
});

function editSessionId(value: unknown): string {
  assert(value && typeof value === 'object' && 'editSessionId' in value);
  const id = value.editSessionId;
  assert(typeof id === 'string');
  return id;
}

function needsConfirmation(value: unknown): boolean {
  return Boolean(value && typeof value === 'object'
    && 'needs_confirmation' in value && value.needs_confirmation === true);
}

const first = new ExternalBridgeRuntime(
  projectId,
  'editor-before-runtime-rebuild',
  context,
  () => undefined,
);
const firstBinding = binding('editor-before-runtime-rebuild');
const sessionId = editSessionId(await first.execute(
  'begin_edit_session',
  { clientName: 'Newma export' },
  firstBinding,
));
const args = { editSessionId: sessionId, limit: 1 };
const guarded = await first.execute('read_export_history', args, firstBinding);
assert.equal(needsConfirmation(guarded), true);
const originalGuard = first.pendingGuard();
assert(originalGuard);

const stored = await loadExternalProposal(projectId);
assert(stored?.status === 'drafting');

await stopAgentRunLeases(projectId);
await loadRecoveredAgentSession(projectId, () => true);

const rebuilt = new ExternalBridgeRuntime(
  projectId,
  'editor-after-runtime-rebuild',
  context,
  () => undefined,
);
await rebuilt.hydrate(stored);

assert.equal(
  rebuilt.pendingGuard()?.id,
  originalGuard.id,
  'a rebuilt editor runtime restores the durable pending confirmation card',
);
assert.equal(
  (await loadAgentRuntimeSidecar(projectId)).approvals
    .find((approval) => approval.approvalId === originalGuard.id)?.status,
  'pending',
  'runtime hydration keeps the unresolved approval pending',
);

await rebuilt.confirmRealTool(originalGuard.id, true);
const exported = await rebuilt.execute(
  'read_export_history',
  args,
  binding('editor-after-runtime-rebuild'),
);
assert.equal(
  needsConfirmation(exported),
  false,
  'the exact retried call consumes the confirmation restored by the new runtime',
);

const handoffArgs = { editSessionId: sessionId, limit: 2 };
assert.equal(
  needsConfirmation(await rebuilt.execute(
    'read_export_history',
    handoffArgs,
    binding('editor-after-runtime-rebuild'),
  )),
  true,
);
const handoffGuard = rebuilt.pendingGuard();
assert(handoffGuard);
const handoff = new ExternalBridgeRuntime(
  projectId,
  'editor-after-live-handoff',
  context,
  () => undefined,
);
const latestStored = await loadExternalProposal(projectId);
assert(latestStored?.status === 'drafting');
await handoff.hydrate(latestStored);
await rebuilt.disconnect();
assert.equal(
  handoff.pendingGuard()?.id,
  handoffGuard.id,
  'the replacement runtime keeps the pending card after predecessor cleanup',
);
assert.equal(
  (await loadAgentRuntimeSidecar(projectId)).approvals
    .find((approval) => approval.approvalId === handoffGuard.id)?.status,
  'pending',
  'predecessor cleanup cannot cancel an approval owned by the replacement runtime',
);
await handoff.confirmRealTool(handoffGuard.id, false);

await Promise.allSettled([first.disconnect(), handoff.disconnect()]);
resetAgentRuntimeStoreMemory();

console.log('external-approval-hydration.verify: durable pending guard restored after runtime rebuild');
