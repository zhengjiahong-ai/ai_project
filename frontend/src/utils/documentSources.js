/** Preserve source identity; never infer the paper from the currently visible PDF. */
export function documentSources(value) {
  const sources = Array.isArray(value?.sources) ? value.sources : Array.isArray(value?.rag_sources) ? value.rag_sources : [];
  const result = [...sources];
  if (value?.sourceAnchorId) result.push({ sourceId: value.sourceAnchorId,
    pdfId: value.sourcePdfId, pageIndex: value.sourcePageIndex, sectionId: value.sourceAnchorId,
    text: value.sourceText || value.content || value.text || '' });
  // Older page artifacts saved a paper association but no detailed excerpt.
  // A page belongs to a single saved paper only; never assign it to all materials.
  if (!result.length && Array.isArray(value?.paperIds)) {
    const paperIds = [...new Set(value.paperIds.filter(id => typeof id === 'string' && id.trim()))];
    for (const pdfId of paperIds) result.push({ pdfId,
      ...(paperIds.length === 1 && Number.isInteger(value?.pageIndex) && value.pageIndex >= 0
        ? { pageIndex: value.pageIndex } : {}) });
  }
  const seen = new Set();
  return result.filter((source) => {
    if (!source || typeof source !== 'object') return false;
    const key = JSON.stringify([source.pdfId || source.sourcePdfId, source.sourceId, source.pageIndex, source.text]);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  }).map((source) => ({ ...source }));
}
