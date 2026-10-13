const storageKey = 'pixiu:pending-research-starts:v2';

function read() {
  try {
    const saved = JSON.parse(globalThis.sessionStorage?.getItem(storageKey) || '{}');
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  } catch { return {}; }
}

function write(value) {
  try { globalThis.sessionStorage?.setItem(storageKey, JSON.stringify(value)); } catch { /* In-memory intent still protects this tab. */ }
}

export function researchIntentKey(taskId, input) {
  const { expectedTaskRevision, ...intent } = input;
  return JSON.stringify([taskId, intent]);
}

export function getResearchIntent(key, input) {
  const saved = read();
  const found = saved[key];
  if (found && typeof found.requestId === 'string' && found.input && typeof found.input === 'object') return found;
  const value = { requestId: globalThis.crypto.randomUUID(), input };
  const entries = Object.entries(saved).slice(-31);
  write({ ...Object.fromEntries(entries), [key]: value });
  return value;
}

export function clearResearchIntent(key) {
  const saved = read();
  delete saved[key];
  write(saved);
}
