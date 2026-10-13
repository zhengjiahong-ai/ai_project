import { documentSources } from './documentSources';

/** Export the current editor text, with saved material identities kept separately. */
export function documentMarkdownExport(document, draft, papers = []) {
  const sources = documentSources(document);
  if (!sources.length) return draft;
  const lines = sources.map(source => {
    const id = source.pdfId || source.sourcePdfId || source.metadata?.id || '';
    const title = papers.find(paper => paper.id === id)?.title || source.title || id || '来源材料';
    const page = Number.isInteger(source.pageIndex) ? `，第 ${source.pageIndex + 1} 页` : '';
    const label = `${title}${page}${source.sourceId ? `，${source.sourceId}` : ''}`;
    return `- ${label.replace(/\r?\n/g, ' ')}`;
  });
  return `${draft}\n\n<details>\n<summary>材料来源</summary>\n\n${lines.join('\n')}\n\n</details>\n`;
}
