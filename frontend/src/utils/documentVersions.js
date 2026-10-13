export const documentText = (document) => `${document?.text ?? document?.content ?? document?.body ?? ''}`;

export function reviseDocument(document, text, { draft, restoredFrom, now = new Date().toISOString() } = {}) {
  const previous = documentText(document);
  const machineResult = document.critique || document.sourceRunId || document.engineVersion === 'deep-research-v2';
  const versions = [...(document.versions || [])];
  if (previous !== text) versions.push({ text: previous, savedAt: now, kind: 'saved',
    ...(document.critique ? { critique: document.critique } : {}),
    ...(machineResult ? { edited: Boolean(document.edited) } : {}) });
  if (draft !== undefined && draft !== previous && draft !== text) {
    versions.push({ text: draft, savedAt: now, kind: 'unsaved-draft' });
  }
  return { ...document, text, versions, updatedAt: now,
    ...(machineResult && previous !== text ? { edited: true } : {}),
    ...(restoredFrom ? { restoredFrom } : {}) };
}
