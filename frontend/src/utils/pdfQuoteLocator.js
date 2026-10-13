const normalized = text => String(text || '').normalize('NFKC').toLowerCase()
  .replace(/-\s*\n\s*/gu, '').replace(/[^\p{L}\p{N}]/gu, '');

/** Locate the complete literal excerpt, never a loose keyword or guessed page. */
export function locateQuotePage(pages, quote) {
  const needle = normalized(quote);
  if (needle.length < 30) return null;
  const matches = pages.flatMap((text, index) => normalized(text).includes(needle) ? [index] : []);
  return matches.length === 1 ? matches[0] : null;
}

const documents = new Map();
export async function locatePdfQuote(blob, paperId, quote) {
  if (!documents.has(paperId)) {
    const loading = (async () => {
      const { getDocument, GlobalWorkerOptions } = await import('pdfjs-dist');
      const { default: worker } = await import('pdfjs-dist/build/pdf.worker.min.js?url');
      GlobalWorkerOptions.workerSrc = worker;
      const task = getDocument({ data: new Uint8Array(await blob.arrayBuffer()) });
      try {
        const pdf = await task.promise;
        const pages = [];
        for (let index = 1; index <= pdf.numPages; index++) {
          const page = await pdf.getPage(index);
          const content = await page.getTextContent();
          pages.push(content.items.map(item => item.str + (item.hasEOL ? '\n' : ' ')).join(''));
        }
        return pages;
      } finally { await task.destroy(); }
    })();
    documents.set(paperId, loading);
    if (documents.size > 8) documents.delete(documents.keys().next().value);
    loading.catch(() => documents.delete(paperId));
  }
  return locateQuotePage(await documents.get(paperId), quote);
}
