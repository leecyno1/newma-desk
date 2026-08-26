import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

export interface Note {
  id: string;
  kind: string;
  title: string;
  content: string;
  ts: number;
}

export interface ResearchRecordWorkspace {
  schemaVersion: "newma-desk.research-records.v1";
  updatedAt: string;
  records: Note[];
}

interface StorageDocument { revision: number; value: unknown }
type RecordMutation = (remote: Note[]) => Note[];

const LOCAL_KEY = "newma-desk.research-records.v1";
const LEGACY_KEY = "vr-notes";
const NAMESPACE = "research-notes";
const DOCUMENT_KEY = "records";
const MAX = 200;

const now = () => new Date().toISOString();
const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown, fallback = "", limit = 120_000) => typeof value === "string" ? value.slice(0, limit) : fallback;

function normalizeNote(value: unknown): Note | null {
  if (!isRecord(value)) return null;
  const title = text(value.title, "", 240).trim();
  const content = text(value.content).trim();
  if (!title || !content) return null;
  return {
    id: text(value.id, `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, 160),
    kind: text(value.kind, "研究记录", 40).trim() || "研究记录",
    title,
    content,
    ts: typeof value.ts === "number" && Number.isFinite(value.ts) ? value.ts : Date.now(),
  };
}

function normalizeRecords(value: unknown) {
  return (Array.isArray(value) ? value : []).map(normalizeNote).filter((item): item is Note => item !== null).sort((a, b) => b.ts - a.ts).slice(0, MAX);
}

function normalizeWorkspace(value: unknown): ResearchRecordWorkspace {
  const row = isRecord(value) ? value : {};
  return {
    schemaVersion: "newma-desk.research-records.v1",
    updatedAt: text(row.updatedAt, now(), 64),
    records: normalizeRecords(row.records),
  };
}

function readJson(key: string) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); }
  catch { return null; }
}

function persistLocal(records: Note[]) {
  const normalized = normalizeRecords(records);
  const workspace: ResearchRecordWorkspace = { schemaVersion: "newma-desk.research-records.v1", updatedAt: now(), records: normalized };
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(workspace));
    localStorage.setItem(LEGACY_KEY, JSON.stringify(normalized));
  } catch { /* local storage can be disabled */ }
  return workspace;
}

export function loadNotes() {
  const current = readJson(LOCAL_KEY);
  if (current) return normalizeWorkspace(current).records;
  const legacy = normalizeRecords(readJson(LEGACY_KEY));
  if (legacy.length) persistLocal(legacy);
  return legacy;
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}
function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}
function endpoint(config: VibeDeskConfig) { return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`; }
function headers(config: VibeDeskConfig, json = false) { return { Authorization: `Bearer ${config.accessToken}`, "X-Newma-Desk-Instance-Id": config.instanceId || "", ...(json ? { "Content-Type": "application/json" } : {}) }; }

async function readRemote(config: VibeDeskConfig) {
  const response = await fetch(endpoint(config), { headers: headers(config) });
  if (response.status === 404) return { found: false, revision: 0, workspace: normalizeWorkspace(null) };
  if (!response.ok) throw new Error(`research records read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { found: true, revision: Number(document.revision) || 0, workspace: normalizeWorkspace(document.value) };
}

function mergeRecords(primary: Note[], secondary: Note[]) {
  const records = new Map<string, Note>();
  for (const note of [...secondary, ...primary]) {
    const previous = records.get(note.id);
    if (!previous || note.ts >= previous.ts) records.set(note.id, note);
  }
  return normalizeRecords([...records.values()]);
}

function recordsEqual(left: Note[], right: Note[]) {
  const normalizedLeft = normalizeRecords(left);
  const normalizedRight = normalizeRecords(right);
  if (normalizedLeft.length !== normalizedRight.length) return false;
  return normalizedLeft.every((note, index) => {
    const other = normalizedRight[index];
    return Boolean(other) &&
      note.id === other.id &&
      note.kind === other.kind &&
      note.title === other.title &&
      note.content === other.content &&
      note.ts === other.ts;
  });
}

async function writeRemote(config: VibeDeskConfig, mutate: RecordMutation) {
  if (!canWrite(config)) return null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const current = await readRemote(config);
      const workspace: ResearchRecordWorkspace = {
        schemaVersion: "newma-desk.research-records.v1",
        updatedAt: now(),
        records: normalizeRecords(mutate(current.workspace.records)),
      };
      const response = await fetch(endpoint(config), {
        method: "PUT",
        headers: headers(config, true),
        body: JSON.stringify({ expectedRevision: current.revision, value: workspace }),
      });
      if (response.status === 409 && attempt < 2) continue;
      if (!response.ok) throw new Error(`research records write failed: ${response.status}`);
      return workspace.records;
    } catch { return null; }
  }
  return null;
}

export async function hydrateNotes() {
  const local = loadNotes();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    if (!remote.found) {
      if (!local.length || !canWrite(config)) return local;
      const stored = await writeRemote(config, (current) => mergeRecords(local, current));
      return persistLocal(stored ?? local).records;
    }
    const merged = mergeRecords(remote.workspace.records, local);
    persistLocal(merged);
    if (recordsEqual(merged, remote.workspace.records) || !canWrite(config)) return merged;
    const stored = await writeRemote(config, (current) => mergeRecords(merged, current));
    return persistLocal(stored ?? merged).records;
  } catch { return local; }
}

function publishChange(records: Note[]) {
  const workspace = persistLocal(records);
  window.dispatchEvent(new CustomEvent("newma:research-records-changed", { detail: workspace }));
  return workspace.records;
}

async function persistMutation(localRecords: Note[], mutateRemote: RecordMutation) {
  let records = publishChange(localRecords);
  const config = await waitForVibeDeskConfig();
  if (config && canWrite(config)) {
    const stored = await writeRemote(config, mutateRemote);
    if (stored) records = publishChange(stored);
  }
  return records;
}

export async function addNote(kind: string, title: string, content: string) {
  const note: Note = {
    id: `note:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`}`,
    kind: kind.trim().slice(0, 40) || "研究记录",
    title: title.trim().slice(0, 240) || "未命名研究记录",
    content: content.trim().slice(0, 120_000),
    ts: Date.now(),
  };
  const local = mergeRecords([note], loadNotes());
  return persistMutation(local, (remote) => mergeRecords(local, remote));
}

export async function deleteNote(id: string) {
  const local = loadNotes().filter((note) => note.id !== id);
  return persistMutation(local, (remote) =>
    mergeRecords(local, remote.filter((note) => note.id !== id))
  );
}

export async function clearNotes() {
  return persistMutation([], () => []);
}
