import { documentDisplayTitle } from './documentPresentation.js';
const savedTime = item => {
  for (const value of [item.updatedAt, item.createdAt, item.timestamp]) {
    if (value === null || value === undefined || value === '') continue;
    const time = new Date(value).getTime();
    if (Number.isFinite(time)) return time;
  }
  return null;
};

export function documentPreview(item) {
  const text = [item.summary, item.text, item.content, item.body].find(value => typeof value === 'string' && value.trim()) || '';
  return text.replace(/(?:^|\n)#{1,6}\s+[^\n]*\n/gu, ' ')
    .replace(/\[\[?\d+\]?\]\(#research-evidence-[^)]+\)/gu, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/gu, '$1').replace(/[*_`#>]/gu, '')
    .replace(/\[(?:\d+[\s,，]*)+\]/gu, '').replace(/\s+/gu, ' ').trim().slice(0, 100);
}

/** Hide immutable machine-origin artifacts when a user-edited or latest-origin
 *  version exists for the same source research. Machine versions remain
 *  accessible through the document version history control. */
function filterMachineArtifactDuplicates(items) {
  const bySource = new Map();
  for (const item of items) {
    const sourceId = item.sourceResearchId || item.sourceRequestId;
    if (!sourceId) continue;
    if (!bySource.has(sourceId)) bySource.set(sourceId, []);
    bySource.get(sourceId).push(item);
  }
  const hidden = new Set();
  for (const [, group] of bySource) {
    if (group.length < 2) continue;
    const hasUserOrLatest = group.some(item => item.origin !== 'machine');
    if (hasUserOrLatest) {
      for (const item of group) {
        if (item.origin === 'machine') hidden.add(item);
      }
    }
  }
  return items.filter(item => !hidden.has(item));
}

// Presentation only: keep the persisted documents, their titles and their order intact.
export function taskDocumentNavigation(task, papers = []) {
  const rawItems = [...(task?.notes || []), ...(task?.artifacts || [])].filter(item => !item.hiddenFromLibrary);
  const items = filterMachineArtifactDuplicates(rawItems);
  const titleOf = item => documentDisplayTitle(item, task, papers);
  const counts = new Map();
  items.forEach(item => counts.set(titleOf(item), (counts.get(titleOf(item)) || 0) + 1));
  const occurrences = new Map();
  return items.map((item, index) => {
    const title = titleOf(item);
    const occurrence = (occurrences.get(title) || 0) + 1;
    occurrences.set(title, occurrence);
    const time = savedTime(item);
    const details = [];
    if (counts.get(title) > 1) {
      if (time !== null) {
        details.push(new Date(time).toLocaleString('zh-CN', {
          month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
        }));
      } else {
        const excerpt = item.source?.text || item.sources?.[0]?.text;
        if (excerpt?.trim()) details.push(excerpt.replace(/\s+/g, ' ').trim().slice(0, 36));
        else details.push(`记录 ${occurrence}`);
      }
    }
    const date = time === null ? '' : new Date(time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
    return { item, title, detail: details.join(' · '), preview: documentPreview(item), date, time, index };
  }).sort((a, b) => {
    if (a.time !== null && b.time !== null) return b.time - a.time || a.index - b.index;
    if (a.time !== null) return -1;
    if (b.time !== null) return 1;
    return a.index - b.index;
  });
}
