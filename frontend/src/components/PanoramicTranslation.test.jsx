import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({getDocument:vi.fn(),draw:vi.fn()}));
vi.mock('pdfjs-dist', () => ({getDocument:mocks.getDocument,GlobalWorkerOptions:{}}));
vi.mock('./MarkdownContent', () => ({default:({children})=><div>{children}</div>}));
import PanoramicTranslation from './PanoramicTranslation';

const data = {translatedBlocks:[{id:'body',translatedText:'完整的中文译文'}],pageLayout:{
  viewport:{width:600,height:800},blocks:[{id:'body',text:'The paragraph describes the method.',
    bbox:{left:0.1,top:0.3,width:0.8,height:0.1}}]}};
const deferred = () => { let resolve; const promise = new Promise(done=>{resolve=done;}); return {promise,resolve}; };
const makePage = (width, completion = Promise.resolve()) => ({getViewport:({scale})=>({width:width*scale,height:800*scale}),
  render:vi.fn(()=>({promise:completion,cancel:vi.fn()}))});

beforeEach(() => {
  mocks.getDocument.mockReset(); mocks.draw.mockReset();
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({drawImage:mocks.draw,
    getImageData:()=>({data:new Uint8ClampedArray([0,0,0,255])})});
});

afterEach(() => {
  delete HTMLDialogElement.prototype.showModal;
});

it('keeps the PDF document while changing pages and cancels old page rendering', async () => {
  const slow = deferred(), first = makePage(600,slow.promise), second = makePage(500);
  const getPage = vi.fn(number=>Promise.resolve(number===1?first:second));
  const destroy = vi.fn(async()=>{});
  mocks.getDocument.mockReturnValue({promise:Promise.resolve({getPage}),destroy});
  const view=render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={0} pageData={data}/>);
  await waitFor(()=>expect(first.render).toHaveBeenCalled());
  view.rerender(<PanoramicTranslation fileUrl="A.pdf" pageIndex={1} pageData={data}/>);
  await waitFor(()=>expect(second.render).toHaveBeenCalled());
  await waitFor(()=>expect(mocks.draw).toHaveBeenCalled());
  expect(first.render.mock.results[0].value.cancel).toHaveBeenCalledOnce();
  expect(mocks.getDocument).toHaveBeenCalledOnce();
  expect(mocks.draw.mock.calls.every(call=>call[0].width===1000)).toBe(true);
  mocks.draw.mockClear();
  await act(async()=>{slow.resolve(); await slow.promise;});
  expect(mocks.draw).not.toHaveBeenCalled();
  view.unmount(); expect(destroy).toHaveBeenCalledOnce();
});

it('does not draw a late result from another paper', async () => {
  const old = deferred(), first=makePage(600,old.promise), second=makePage(450);
  const destroyA=vi.fn(async()=>{});
  mocks.getDocument.mockImplementation(({url})=>({promise:Promise.resolve({getPage:async()=>url==='A.pdf'?first:second}),
    destroy:url==='A.pdf'?destroyA:vi.fn(async()=>{})}));
  const view=render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={0} pageData={data}/>);
  await waitFor(()=>expect(first.render).toHaveBeenCalled());
  view.rerender(<PanoramicTranslation fileUrl="B.pdf" pageIndex={0} pageData={data}/>);
  await waitFor(()=>expect(mocks.draw).toHaveBeenCalled());
  expect(mocks.draw.mock.calls.every(call=>call[0].width===900)).toBe(true);
  mocks.draw.mockClear();
  await act(async()=>{old.resolve(); await old.promise;});
  expect(mocks.draw).not.toHaveBeenCalled();
  expect(destroyA).toHaveBeenCalledOnce();
});

it('keeps the completed translation readable when source PDF rendering fails', async () => {
  mocks.getDocument.mockReturnValue({promise:Promise.reject(new Error('unavailable')),destroy:vi.fn(async()=>{})});
  render(<PanoramicTranslation fileUrl="missing.pdf" pageIndex={0} pageData={data}/>);
  expect(await screen.findByText('原图暂时无法显示，请切回原文查看。')).toBeInTheDocument();
  expect(screen.getByText('完整的中文译文')).toBeInTheDocument();
});

it('clears a failed page when navigating and keeps the same PDF document', async () => {
  const next = deferred();
  const getPage = vi.fn(number => number === 1 ? Promise.reject(new Error('bad page')) : next.promise);
  mocks.getDocument.mockReturnValue({promise:Promise.resolve({getPage}),destroy:vi.fn(async()=>{})});
  const view = render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={0} pageData={data}/>);
  expect(await screen.findByText('原图暂时无法显示，请切回原文查看。')).toBeInTheDocument();
  view.rerender(<PanoramicTranslation fileUrl="A.pdf" pageIndex={1} pageData={data}/>);
  expect(screen.queryByText('原图暂时无法显示，请切回原文查看。')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('正在载入原图');
  await act(async()=>{next.resolve(makePage(500));});
  await waitFor(()=>expect(screen.queryByRole('status')).not.toBeInTheDocument());
  expect(mocks.getDocument).toHaveBeenCalledOnce();
});

it('does not retain the old document error while a different PDF is loading', async () => {
  const next = deferred();
  mocks.getDocument.mockImplementation(({url})=>({promise:url==='A.pdf'
    ? Promise.reject(new Error('missing')) : next.promise,destroy:vi.fn(async()=>{})}));
  const view = render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={0} pageData={data}/>);
  expect(await screen.findByText('原图暂时无法显示，请切回原文查看。')).toBeInTheDocument();
  view.rerender(<PanoramicTranslation fileUrl="B.pdf" pageIndex={0} pageData={data}/>);
  expect(screen.getByRole('status')).toHaveTextContent('正在载入原图');
  await act(async()=>{next.resolve({getPage:async()=>makePage(500)});});
  await waitFor(()=>expect(screen.queryByRole('status')).not.toBeInTheDocument());
});

it('shows unpositioned cached prose before a folded original page without rewriting it', async () => {
  mocks.getDocument.mockReturnValue({promise:Promise.resolve({getPage:async()=>makePage(600)}),destroy:vi.fn(async()=>{})});
  const text = '保留已有译文，公式错误也不擅自改写。';
  render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={3} pageData={{translatedText:text,translatedBlocks:[]}}/>);
  expect(screen.getByText(text)).toBeInTheDocument();
  const summary = await screen.findByText('查看整页原图与公式');
  expect(summary.closest('details')).not.toHaveAttribute('open');
  expect(screen.getByText(text).compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  fireEvent.click(summary);
  expect(summary.closest('details')).toHaveAttribute('open');
  expect(screen.getByRole('img',{name:'论文原图、公式或尚未翻译内容'})).toBeVisible();
});

it('keeps unmatched cached text readable but does not attach it to unrelated paragraph coordinates', async () => {
  mocks.getDocument.mockReturnValue({promise:Promise.reject(new Error('unavailable')),destroy:vi.fn(async()=>{})});
  render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={3} pageData={{...data,
    translatedText:'无坐标的已有正文',translatedBlocks:[{id:'old-id',translatedText:'无坐标的已有正文'}]}}/>);
  expect(screen.getByText('无坐标的已有正文')).toBeInTheDocument();
  expect(screen.getByText('译文未按段落定位，可展开原图核对。')).toBeInTheDocument();
  expect(await screen.findByText('原图暂时无法显示，请切回原文查看。')).toBeInTheDocument();
});

it('opens a local enlargement of the original image without loading another document', async () => {
  const show = vi.fn(function(){this.open=true;});
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:show});
  mocks.getDocument.mockReturnValue({promise:Promise.resolve({getPage:async()=>makePage(600)}),destroy:vi.fn(async()=>{})});
  render(<PanoramicTranslation fileUrl="A.pdf" pageIndex={0} pageData={data}/>);
  await waitFor(()=>expect(mocks.draw).toHaveBeenCalled());
  fireEvent.click(screen.getAllByRole('button',{name:'放大论文原图、公式或尚未翻译内容'})[0]);
  expect(show).toHaveBeenCalledOnce();
  expect(screen.getByRole('dialog',{name:'原图放大查看'})).toBeVisible();
  expect(mocks.getDocument).toHaveBeenCalledOnce();
});
