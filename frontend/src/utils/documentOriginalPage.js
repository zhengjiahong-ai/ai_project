import { documentSources } from './documentSources';

/** Only an unambiguous saved page can be rendered; reading focus is irrelevant. */
export function documentOriginalPage(document) {
  const sources = documentSources(document);
  const pages = new Map();
  for (const source of sources) {
    const pdfId = source.pdfId || source.sourcePdfId;
    if (!pdfId || !Number.isInteger(source.pageIndex) || source.pageIndex < 0) return null;
    pages.set(JSON.stringify([pdfId, source.pageIndex]), { pdfId, pageIndex: source.pageIndex });
  }
  return pages.size === 1 ? [...pages.values()][0] : null;
}
