import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ getDocument: vi.fn() }));
vi.mock('pdfjs-dist', () => ({ getDocument: mocks.getDocument, GlobalWorkerOptions: {} }));
import { pdfPageDataUrl } from './pdfPageExport';

const blob = () => Object.assign(new Blob(['pdf']), { arrayBuffer: async () => new Uint8Array([1, 2]).buffer });
beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({});
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,YQ==');
});
it('renders the saved page number and releases the PDF after obtaining its pixels', async () => {
  const render = vi.fn(() => ({ promise: Promise.resolve() }));
  const getPage = vi.fn(async () => ({ getViewport: ({ scale }) => ({ width: 600 * scale, height: 800 * scale }), render }));
  const destroy = vi.fn(async () => {});
  mocks.getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 5, getPage }), destroy });
  expect(await pdfPageDataUrl(blob(), 3)).toBe('data:image/png;base64,YQ==');
  expect(getPage).toHaveBeenCalledWith(4);
  expect(render.mock.calls[0][0].viewport).toEqual({ width: 1800, height: 2400 });
  expect(destroy).toHaveBeenCalledOnce();
});
it('rejects an out-of-range source page and destroys the document without rendering', async () => {
  const getPage = vi.fn(), destroy = vi.fn(async () => {});
  mocks.getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 2, getPage }), destroy });
  await expect(pdfPageDataUrl(blob(), 3)).rejects.toThrow('保存的页码超出论文范围');
  expect(getPage).not.toHaveBeenCalled();
  expect(destroy).toHaveBeenCalledOnce();
});
it('does not produce an export image after the source operation is cancelled', async () => {
  const abort = new AbortController();
  abort.abort();
  await expect(pdfPageDataUrl(blob(), 0, abort.signal)).rejects.toThrow();
  expect(mocks.getDocument).not.toHaveBeenCalled();
});
