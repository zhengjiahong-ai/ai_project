import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';

GlobalWorkerOptions.workerSrc = workerUrl;

/** Render actual PDF pixels rather than rebuilding mathematics from extracted text. */
export async function pdfPageDataUrl(blob, pageIndex, signal) {
  if (!(blob instanceof Blob) || !Number.isInteger(pageIndex) || pageIndex < 0) throw new Error('原图来源无效');
  signal?.throwIfAborted();
  const bytes = new Uint8Array(await blob.arrayBuffer());
  signal?.throwIfAborted();
  const loading = getDocument({ data: bytes });
  const abort = () => { void loading.destroy().catch(() => {}); };
  signal?.addEventListener('abort', abort, { once: true });
  try {
    const pdf = await loading.promise;
    signal?.throwIfAborted();
    if (pageIndex >= pdf.numPages) throw new Error('保存的页码超出论文范围');
    const page = await pdf.getPage(pageIndex + 1);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: Math.min(3, 1800 / base.width) });
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport, background: '#ffffff' }).promise;
    signal?.throwIfAborted();
    return canvas.toDataURL('image/png');
  } finally {
    signal?.removeEventListener('abort', abort);
    await loading.destroy().catch(() => {});
  }
}
