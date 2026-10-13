/** Plain-text previews only: retained content is never rewritten or interpreted. */
export function documentSearchText(item) {
  const sourceText = source => [source?.title, source?.pdfId, source?.workId, source?.versionId,
    source?.doi, source?.arxivId, source?.quote, source?.text, source?.section].filter(value => typeof value === 'string').join(' ');
  return [item.title, item.text, item.content, item.body, item.summary, item.aiInterpretation,
    sourceText(item.source), ...(item.sources || []).map(sourceText)].filter(value => typeof value === 'string').join(' ');
}

export function searchExcerpt(value, query) {
  const text = String(value || '').replace(/(\*\*|__|`)([^\n]*?)\1/gu, '$2').replace(/(?:^|\n)#{1,6}\s+/gu, ' ').replace(/\s+/gu, ' ').trim();
  const term = String(query || '').trim();
  if (!term) return '';
  const index = text.toLocaleLowerCase().indexOf(term.toLocaleLowerCase());
  if (index < 0) return '';
  const start = Math.max(0, index - 24), end = Math.min(text.length, index + term.length + 52);
  return `${start ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`;
}

const visitKey = taskId => `pixiu-navigation-visits:${JSON.stringify(taskId)}`;
export function readNavigationVisits(taskId) {
  try {
    const items = JSON.parse(localStorage.getItem(visitKey(taskId)) || '[]');
    return Array.isArray(items) ? items.filter(item => ['paper', 'document', 'learning'].includes(item?.kind) && typeof item.id === 'string').slice(0, 12) : [];
  } catch { return []; }
}
export function rememberNavigationVisit(taskId, visit) {
  if (!taskId || !visit?.id) return [];
  const items = [visit, ...readNavigationVisits(taskId).filter(item => item.kind !== visit.kind || item.id !== visit.id)].slice(0, 12);
  try { localStorage.setItem(visitKey(taskId), JSON.stringify(items)); } catch { /* Optional local history. */ }
  return items;
}
