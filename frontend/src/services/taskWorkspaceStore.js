import { initDB } from './localDb.js';

const TASK_STORE = 'taskWorkspaceStore';
const META_STORE = 'metaStore';
const MIGRATION_KEY = 'legacyPaperTasks:v1';
const paperMigrationKey = (paperId) => `legacyPaperTask:${paperId}`;
let migrationPromise = null;

const now = () => new Date().toISOString();
const asArray = (value) => (Array.isArray(value) ? value : []);

// A deterministic namespace survives an interrupted import and avoids long path IDs.
const legacyDocumentNamespace = (taskId) => {
  let hash = 0x6c62272e07bb014262b821756295c58dn;
  for (const character of taskId) {
    hash ^= BigInt(character.codePointAt(0));
    hash = BigInt.asUintN(128, hash * 0x1000000000000000000013bn);
  }
  return hash.toString(16).padStart(32, '0');
};

export function identifyLegacyDocuments(task) {
  const namespace = legacyDocumentNamespace(task.id);
  const used = new Set(['notes', 'artifacts'].flatMap(field => asArray(task[field])
    .flatMap(item => [item?.id, item?.artifactId]).filter(Boolean)));
  const identify = (field) => asArray(task[field]).map((item, index) => {
    if (!item || typeof item !== 'object' || item.id || item.artifactId) return item;
    const base = `legacy-document:${namespace}:${field}:${index}`;
    let id = base;
    let suffix = 0;
    while (used.has(id)) id = `${base}:${++suffix}`;
    used.add(id);
    return { ...item, id };
  });
  return { ...task, notes: identify('notes'), artifacts: identify('artifacts') };
}

// Provenance is inferred only from a legacy store key or an explicit source field.
export function patchLegacyProvenance(task, legacyPaperId = null) {
  task = identifyLegacyDocuments(task);
  const source = (item) => item?.paperId || item?.pdfId || legacyPaperId;
  return {
    ...task,
    messages: asArray(task.messages).map((message) => {
      const paperId = source(message);
      if (!paperId || !message || typeof message !== 'object') return message;
      if (message.context) return { ...message, taskId: message.taskId || task.id,
        context: { ...message.context, taskId: message.context.taskId || task.id } };
      return { ...message, taskId: message.taskId || task.id, context: {
        taskId: task.id, allowedPaperIds: [paperId], primaryPaperId: paperId, strictScope: true,
      } };
    }),
    notes: asArray(task.notes).map((note) => source(note) && !asArray(note?.paperIds).length
      ? { ...note, paperIds: [source(note)] } : note),
    artifacts: asArray(task.artifacts).map((artifact) => source(artifact) && !asArray(artifact?.paperIds).length
      ? { ...artifact, paperIds: [source(artifact)] } : artifact),
  };
}

const taskId = () =>
  `task:${globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`}`;

function normalizeTask(task) {
  if (!task || typeof task.id !== 'string' || !task.id.trim()) {
    throw new Error('任务 ID 不能为空');
  }
  const paperIds = [...new Set(asArray(task.paperIds))];
  if (paperIds.some((id) => typeof id !== 'string' || !id.trim())) {
    throw new Error('论文 ID 必须是非空字符串');
  }
  const focusedPaperId = task.focusedPaperId ?? null;
  if (focusedPaperId && !paperIds.includes(focusedPaperId)) {
    throw new Error('阅读焦点必须属于当前任务');
  }
  if (task.messages !== undefined && !Array.isArray(task.messages)) {
    throw new Error('任务消息必须是数组');
  }
  if (task.notes !== undefined && !Array.isArray(task.notes)) {
    throw new Error('任务笔记必须是数组');
  }
  if (task.artifacts !== undefined && !Array.isArray(task.artifacts)) {
    throw new Error('任务成果必须是数组');
  }
  return {
    ...task,
    id: task.id,
    title: String(task.title || '未命名任务').trim() || '未命名任务',
    paperIds,
    messages: asArray(task.messages),
    notes: asArray(task.notes),
    artifacts: asArray(task.artifacts),
    focusedPaperId,
    activeActivity: task.activeActivity ?? null,
    updatedAt: now(),
  };
}

/**
 * Copy each paper from the old workspace into one task. A deterministic task ID and
 * membership check make retries safe, including retries after a failed write.
 * Legacy stores remain untouched for the old reader and for rollback.
 */
async function runLegacyPaperMigration() {
  const db = await initDB();
  const [libraryEntries, pdfKeys, existingTasks] = await Promise.all([
    db.getAll('libraryStore'),
    db.getAllKeys('pdfStore'),
    db.getAll(TASK_STORE),
  ]);
  const entries = new Map();
  for (const entry of libraryEntries) {
    if (typeof entry?.id === 'string' && entry.id) entries.set(entry.id, entry);
  }
  for (const key of pdfKeys) {
    if (typeof key === 'string' && key && !entries.has(key)) entries.set(key, { id: key });
  }

  const assigned = new Set(existingTasks.flatMap((task) => asArray(task.paperIds)));
  const existingIds = new Set(existingTasks.map((task) => task.id));
  // v1 markers must not skip this additive repair of already copied records.
  for (const task of existingTasks) {
    const legacyPaperId = task.id.startsWith('legacy:') ? task.id.slice(7) : null;
    const repaired = patchLegacyProvenance(task, legacyPaperId);
    if (JSON.stringify(repaired) !== JSON.stringify(task)) {
      await db.put(TASK_STORE, repaired, task.id);
    }
  }
  let migrated = 0;
  for (const [paperId, entry] of entries) {
    const markerKey = paperMigrationKey(paperId);
    if (await db.get(META_STORE, markerKey)) continue;
    const id = `legacy:${paperId}`;
    if (assigned.has(paperId) || existingIds.has(id)) {
      await db.put(META_STORE, { migratedAt: now(), taskId: assigned.has(paperId) ? null : id }, markerKey);
      continue;
    }
    const [history, notes, artifacts, storedPdf] = await Promise.all([
      db.get('historyStore', paperId),
      db.get('notesStore', paperId),
      db.get('artifactStore', paperId),
      db.get('pdfStore', paperId),
    ]);
    const title = entry.filename || entry.title || storedPdf?.name || '未命名论文';
    const legacyUpdatedAt = Number(entry.timestamp);
    const updatedAt = Number.isFinite(legacyUpdatedAt) && legacyUpdatedAt > 0
      ? new Date(legacyUpdatedAt).toISOString()
      : now();
    const task = {
      id,
      title,
      paperIds: [paperId],
      messages: asArray(history),
      notes: asArray(notes),
      artifacts: asArray(artifacts),
      focusedPaperId: paperId,
      activeActivity: null,
      updatedAt,
    };
    await db.put(TASK_STORE, patchLegacyProvenance(task, paperId), id);
    await db.put(META_STORE, { migratedAt: now(), taskId: id }, markerKey);
    assigned.add(paperId);
    existingIds.add(id);
    migrated += 1;
  }
  await db.put(META_STORE, { completedAt: now(), paperCount: entries.size }, MIGRATION_KEY);
  return migrated;
}

export function migrateLegacyPaperTasks() {
  if (!migrationPromise) {
    migrationPromise = runLegacyPaperMigration().finally(() => { migrationPromise = null; });
  }
  return migrationPromise;
}

export async function listTasks() {
  await migrateLegacyPaperTasks();
  const db = await initDB();
  const tasks = await db.getAll(TASK_STORE);
  return tasks.sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

export async function getTask(id) {
  if (typeof id !== 'string' || !id) throw new Error('任务 ID 不能为空');
  await migrateLegacyPaperTasks();
  const db = await initDB();
  return (await db.get(TASK_STORE, id)) ?? null;
}

export async function createTask(input = {}) {
  const task = normalizeTask({ ...input, id: taskId() });
  const db = await initDB();
  await db.put(TASK_STORE, task, task.id);
  return task;
}

export async function saveTask(input) {
  const task = normalizeTask(input);
  const db = await initDB();
  await db.put(TASK_STORE, task, task.id);
  return task;
}

/** Cache server responses without changing their authoritative timestamp/revision. */
export async function cacheTask(task) {
  const db = await initDB();
  await db.put(TASK_STORE, task, task.id);
  return task;
}

export async function replaceServerCache(tasks) {
  const db = await initDB();
  const tx = db.transaction(TASK_STORE, 'readwrite');
  const store = tx.objectStore(TASK_STORE);
  for (const task of await store.getAll()) {
    if (task.revision !== undefined && !tasks.some((remote) => remote.id === task.id)) await store.delete(task.id);
  }
  for (const task of tasks) await store.put(task, task.id);
  await tx.done;
}

export async function retainUnsyncedDraft(task, reason) {
  const db = await initDB();
  const key = `taskDraft:${task.id}`;
  const tx = db.transaction(META_STORE, 'readwrite');
  const store = tx.objectStore(META_STORE);
  const previous = await store.get(key);
  const versions = previous?.versions || (previous?.task ? [{ task: previous.task, reason: previous.reason, savedAt: previous.savedAt }] : []);
  const draft = { task, reason, savedAt: now() };
  if (!versions.some((version) => JSON.stringify(version.task) === JSON.stringify(task))) versions.push(draft);
  await store.put({ ...draft, versions }, key);
  await tx.done;
}

export async function getUnsyncedDraft(id) {
  const db = await initDB();
  return (await db.get(META_STORE, `taskDraft:${id}`)) ?? null;
}

export async function listUnsyncedDrafts() {
  const db = await initDB();
  const tx = db.transaction(META_STORE, 'readonly');
  const keys = await tx.store.getAllKeys();
  const values = await Promise.all(keys.filter(key => typeof key === 'string' && key.startsWith('taskDraft:')).map(key => tx.store.get(key)));
  await tx.done;
  return values.filter(Boolean).sort((a, b) => Date.parse(b.savedAt) - Date.parse(a.savedAt));
}

export async function clearUnsyncedDraft(id) {
  const db = await initDB();
  await db.delete(META_STORE, `taskDraft:${id}`);
}
