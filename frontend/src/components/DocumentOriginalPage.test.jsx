import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ file: vi.fn(), render: vi.fn(), html: vi.fn() }));
vi.mock('../services/taskWorkspaceApi', () => ({ taskWorkspaceApi: { getMaterialFile: mocks.file } }));
vi.mock('../utils/pdfPageExport', () => ({ pdfPageDataUrl: mocks.render }));
vi.mock('../utils/documentHtmlExport', () => ({ documentHtmlExport: mocks.html }));
import DocumentOriginalPage from './DocumentOriginalPage';

const props = { taskId: 'task-A', source: { pdfId: 'A', pageIndex: 3 }, title: '译文', paperTitle: '论文甲', text: '当前正文' };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.file.mockResolvedValue(new Blob(['pdf']));
  mocks.render.mockResolvedValue('data:image/png;base64,YQ==');
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); });
it('loads only after explicit expansion and downloads the current draft and saved original identity', async () => {
  const view = render(<DocumentOriginalPage {...props} />);
  expect(mocks.file).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('原图与图文下载 · 第 4 页'));
  expect(await screen.findByRole('img', { name: '论文甲第 4 页原图' })).toBeVisible();
  expect(mocks.file).toHaveBeenCalledWith('task-A', 'A');
  expect(mocks.render).toHaveBeenCalledWith(expect.any(Blob), 3, expect.any(AbortSignal));
  view.rerender(<DocumentOriginalPage {...props} text="未保存的新正文" />);
  mocks.html.mockReturnValue('<html>saved original</html>');
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  vi.useFakeTimers();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '下载图文 HTML' })));
  expect(mocks.html).toHaveBeenCalledWith(expect.objectContaining({ text: '未保存的新正文', pdfId: 'A', pageIndex: 3 }));
  expect(click).toHaveBeenCalledOnce();
  vi.runAllTimers();
});
it('ignores a late original from another task and renders the new saved page', async () => {
  let resolve;
  mocks.file.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const view = render(<DocumentOriginalPage {...props} />);
  fireEvent.click(screen.getByText('原图与图文下载 · 第 4 页'));
  await waitFor(() => expect(mocks.file).toHaveBeenCalledOnce());
  view.rerender(<DocumentOriginalPage {...props} taskId="task-B" source={{ pdfId: 'B', pageIndex: 1 }} paperTitle="论文乙" />);
  expect(await screen.findByRole('img', { name: '论文乙第 2 页原图' })).toBeVisible();
  await act(async () => { resolve(new Blob(['old'])); });
  expect(mocks.render).toHaveBeenCalledTimes(1);
  expect(mocks.render.mock.calls[0][1]).toBe(1);
  expect(screen.queryByRole('img', { name: '论文甲第 4 页原图' })).not.toBeInTheDocument();
});
it('shows source failure without enabling an incomplete export or altering the text', async () => {
  mocks.file.mockRejectedValue(new Error('论文文件暂不可用'));
  render(<DocumentOriginalPage {...props} />);
  fireEvent.click(screen.getByText('原图与图文下载 · 第 4 页'));
  expect(await screen.findByRole('alert')).toHaveTextContent('论文文件暂不可用');
  expect(screen.queryByRole('button', { name: '下载图文 HTML' })).not.toBeInTheDocument();
  expect(mocks.render).not.toHaveBeenCalled();
});
