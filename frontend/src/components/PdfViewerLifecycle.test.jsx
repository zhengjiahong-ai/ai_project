import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({ viewer: null, mounts: 0, jump: vi.fn(), zoom: vi.fn(), loadError: false, cachedDoc: null }));
vi.mock('@react-pdf-viewer/core', () => ({ SpecialZoomLevel: { PageWidth: 'PageWidth' }, Worker: ({ children }) => children, Viewer: props => {
  state.viewer = props;
  const initial = React.useRef(props);
  React.useEffect(() => {
    state.mounts += 1;
    const loadedProps = initial.current;
    loadedProps.plugins.forEach(plugin => plugin.install?.({ jumpToPage: state.jump, zoom: state.zoom }));
    if (state.cachedDoc) loadedProps.onDocumentLoad({doc: state.cachedDoc});
    return () => loadedProps.plugins.forEach(plugin => plugin.uninstall?.({}));
  }, []);
  return state.loadError ? props.renderError({name:'InvalidPDFException',message:'broken'}) : <div className="rpv-core__inner-pages" data-testid="pdf-scroll">{props.plugins.map((plugin, index) => <React.Fragment key={index}>{plugin.renderHighlights?.({pageIndex:0,rotation:0,getCssProperties:()=>({})})}</React.Fragment>)}</div>;
} }));
vi.mock('@react-pdf-viewer/highlight', () => ({ highlightPlugin: options => options }));
vi.mock('../services/highlightStore', () => ({ loadHighlights: async () => [], addHighlight: vi.fn(), deleteHighlight: vi.fn() }));
import PdfViewer from './PdfViewer';

beforeEach(() => { state.mounts = 0; state.jump.mockReset(); state.zoom.mockReset(); state.loadError = false; state.cachedDoc = null; localStorage.clear(); });
const viewport = { width: 600, height: 800 };
const textContent = text => ({ items: [{ str: text, transform: [1, 0, 0, 12, 20, 700], width: 100, height: 12 }], styles: {} });

it('accepts a cached document loading before the parent passive effects', async () => {
  state.cachedDoc = {numPages:19,getPage:async()=>({getViewport:()=>viewport,getTextContent:async()=>textContent('cached page')})};
  const pageChange = vi.fn();
  const extracted = vi.fn();
  const view = render(<PdfViewer fileUrl="cached.pdf" pdfId="A" targetPageIndex={3} onPageChange={pageChange} onPageTextExtracted={extracted}/>);
  expect(pageChange).toHaveBeenCalledWith({pageIndex:3,totalPages:19});
  expect(screen.getByRole('button',{name:'放大原文'})).toBeEnabled();
  await act(async()=>{});
  expect(extracted).toHaveBeenCalledWith(expect.objectContaining({pageIndex:3,pageText:'cached page'}));
  view.rerender(<PdfViewer fileUrl="cached.pdf" pdfId="A" targetPageIndex={4} targetPageJumpToken={1}/>);
  expect(state.jump).toHaveBeenLastCalledWith(4);
});

it('keeps a cached document ready through Strict Mode effect replay', async () => {
  state.cachedDoc = {numPages:19,getPage:async()=>({getViewport:()=>viewport,getTextContent:async()=>textContent('cached page')})};
  const pageChange = vi.fn();
  const view = render(<React.StrictMode><PdfViewer fileUrl="cached.pdf" pdfId="A" targetPageIndex={3} onPageChange={pageChange}/></React.StrictMode>);
  await act(async()=>{});
  expect(pageChange).toHaveBeenCalledWith({pageIndex:3,totalPages:19});
  expect(screen.getByRole('button',{name:'放大原文'})).toBeEnabled();
  view.rerender(<React.StrictMode><PdfViewer fileUrl="cached.pdf" pdfId="A" targetPageIndex={4} targetPageJumpToken={1}/></React.StrictMode>);
  expect(state.jump).toHaveBeenLastCalledWith(4);
});

it('zooms a loaded paper and fits its width without remounting or changing page', async () => {
  const doc = {numPages:19,getPage:async()=>({getViewport:()=>viewport,getTextContent:async()=>textContent('body')})};
  render(<PdfViewer fileUrl="fixture.pdf" pdfId="A" targetPageIndex={3} />);
  expect(screen.getByRole('button',{name:'放大原文'})).toBeDisabled();
  await act(async()=>state.viewer.onDocumentLoad({doc}));
  act(()=>state.viewer.onZoom({scale:0.8}));
  fireEvent.click(screen.getByRole('button',{name:'放大原文'}));
  expect(state.zoom).toHaveBeenLastCalledWith(1);
  act(()=>state.viewer.onZoom({scale:1}));
  fireEvent.click(screen.getByRole('button',{name:'缩小原文'}));
  expect(state.zoom).toHaveBeenLastCalledWith(0.8);
  fireEvent.click(screen.getByRole('button',{name:'适合宽度'}));
  expect(state.zoom).toHaveBeenLastCalledWith('PageWidth');
  expect(state.mounts).toBe(1);
  expect(state.viewer.initialPage).toBe(3);
});

it('shows the load error instead of leaving it hidden behind the loading state', () => {
  state.loadError = true;
  render(<PdfViewer fileUrl="broken.pdf" pdfId="A" />);
  expect(screen.getByRole('alert')).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('检查文件是否完整或重新上传');
  expect(screen.getByRole('button',{name:'放大原文'})).toBeDisabled();
});

it('keeps an image-only page readable and clears its text notice after changing to a text page', async () => {
  const doc={numPages:2,getPage:async number=>({getViewport:()=>viewport,
    getTextContent:async()=>number===1?{items:[],styles:{}}:textContent('readable paragraph')})};
  render(<PdfViewer fileUrl="image-page.pdf" pdfId="A"/>);
  await act(async()=>state.viewer.onDocumentLoad({doc}));
  expect(screen.getByRole('status')).toHaveTextContent('当前页没有可选文字');
  expect(screen.getByRole('button',{name:'放大原文'})).toBeEnabled();
  await act(async()=>state.viewer.onPageChange({currentPage:1,doc}));
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

it('jumps through the installed viewer without remounting the document', async () => {
  const doc = { numPages: 19, getPage: async () => ({ getViewport: () => viewport, getTextContent: async () => textContent('body') }) };
  const view = render(<PdfViewer fileUrl="fixture.pdf" pdfId="A" targetPageIndex={0} targetPageJumpToken={0} />);
  await act(async () => state.viewer.onDocumentLoad({ doc }));
  view.rerender(<PdfViewer fileUrl="fixture.pdf" pdfId="A" targetPageIndex={3} targetPageJumpToken={1} />);
  expect(state.mounts).toBe(1);
  expect(state.jump).toHaveBeenLastCalledWith(3);
});

it('publishes page controls when a PDF finished loading behind a restored artifact', async () => {
  const doc = { numPages: 19, getPage: async () => ({ getViewport: () => viewport, getTextContent: async () => textContent('body') }) };
  const pageChange = vi.fn();
  const props = { fileUrl: 'fixture.pdf', pdfId: 'A', targetPageIndex: 3, onPageChange: pageChange };
  const view = render(<PdfViewer {...props} active={false} />);
  await act(async () => state.viewer.onDocumentLoad({ doc }));
  expect(pageChange).not.toHaveBeenCalled();
  view.rerender(<PdfViewer {...props} active />);
  await waitFor(() => expect(pageChange).toHaveBeenCalledWith({ pageIndex: 3, totalPages: 19 }));
  expect(state.mounts).toBe(1);
});

it('ignores text extraction from an old page and from an unmounted document', async () => {
  const finished = {};
  const doc = { numPages: 2, getPage: async number => ({ getViewport: () => viewport,
    getTextContent: () => new Promise(resolve => { finished[number] = resolve; }) }) };
  const extracted = vi.fn();
  const view = render(<PdfViewer fileUrl="fixture.pdf" pdfId="A" onPageTextExtracted={extracted} />);
  await act(async () => state.viewer.onDocumentLoad({ doc }));
  await act(async () => state.viewer.onPageChange({ currentPage: 1, doc }));
  await act(async () => finished[2](textContent('latest page')));
  await act(async () => finished[1](textContent('late old page')));
  expect(extracted).toHaveBeenCalledTimes(1);
  expect(extracted.mock.calls[0][0].pageIndex).toBe(1);
  await act(async () => state.viewer.onPageChange({ currentPage: 0, doc }));
  view.unmount();
  await act(async () => finished[1](textContent('late unmounted page')));
  expect(extracted).toHaveBeenCalledTimes(1);
});

const highlight = {id:1,sourceAnchorId:'anchor-1',text:'selected phrase',position:{pageIndex:0,top:10,left:10,width:20,height:3},
  highlightAreas:[{pageIndex:0,top:10,left:10,width:20,height:3}],actionId:'explain',actionLabel:'解释',
  chatHistory:[{role:'user',content:'selected phrase'},{role:'ai',content:'A'.repeat(260)+'完整解释末尾'}]};
const readyDoc = {numPages:2,getPage:async()=>({getViewport:()=>viewport,getTextContent:async()=>textContent('body')})};

it('keeps color controls beside selection actions and saves a reopenable highlight', async () => {
  render(<PdfViewer fileUrl="A.pdf" pdfId="A" />);
  await act(async () => state.viewer.onDocumentLoad({doc: readyDoc}));
  const cancel = vi.fn();
  const target = state.viewer.plugins.find(plugin => plugin.renderHighlightTarget).renderHighlightTarget({
    selectedText: 'selected phrase', selectionRegion: highlight.position,
    highlightAreas: highlight.highlightAreas, cancel,
  });
  const menu = render(target);
  expect(screen.getByRole('group', {name: '高亮颜色'}).closest('.inline-context-menu'))
    .toBe(screen.getByRole('button', {name: '解释', exact: true}).closest('.inline-context-menu'));
  fireEvent.click(screen.getByRole('button', {name: '黄色', exact: true}));
  expect(cancel).toHaveBeenCalledOnce();
  menu.unmount();
  fireEvent.click(screen.getByRole('button', {name: '查看划线解释：selected phrase'}));
  expect(screen.getByRole('dialog')).toHaveTextContent('文本高亮标记');
});

it('collapses long explanations and closes them on Escape, page changes and hidden readers without deleting highlights', async () => {
  const props = {fileUrl:'A.pdf',pdfId:'A',initialHighlights:[highlight]};
  const view = render(<PdfViewer {...props}/>);
  await act(async()=>state.viewer.onDocumentLoad({doc:readyDoc}));
  const reopen = () => fireEvent.click(screen.getByRole('button',{name:'查看划线解释：selected phrase'}));
  reopen();
  expect(screen.getByRole('dialog')).not.toHaveTextContent('完整解释末尾');
  fireEvent.click(screen.getByRole('button',{name:'展开完整解释'}));
  expect(screen.getByRole('dialog')).toHaveTextContent('完整解释末尾');
  fireEvent.keyDown(document,{key:'Escape'});
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  reopen();
  await act(async()=>state.viewer.onPageChange({currentPage:1,doc:readyDoc}));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  reopen();
  view.rerender(<PdfViewer {...props} active={false}/>);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  view.rerender(<PdfViewer {...props} active/>);
  reopen();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  view.rerender(<PdfViewer {...props} readingKey="other-task:A"/>);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('persists independent reading positions and ignores callbacks while hidden', async () => {
  const pageChange=vi.fn(), extracted=vi.fn();
  const props={fileUrl:'A.pdf',pdfId:'A',readingKey:'task:A',onPageChange:pageChange,onPageTextExtracted:extracted};
  const view=render(<PdfViewer {...props}/>);
  await act(async()=>state.viewer.onDocumentLoad({doc:readyDoc}));
  act(()=>state.viewer.onZoom({scale:1.4}));
  const scroller=screen.getByTestId('pdf-scroll');
  scroller.scrollTop=735; scroller.scrollLeft=24;
  fireEvent.scroll(scroller);
  expect(JSON.parse(localStorage.getItem('pdf-reading:task:A'))).toEqual({scale:1.4,top:735,left:24});
  view.rerender(<PdfViewer {...props} active={false}/>);
  pageChange.mockClear(); extracted.mockClear();
  await act(async()=>state.viewer.onPageChange({currentPage:1,doc:readyDoc}));
  act(()=>state.viewer.onZoom({scale:0.5}));
  scroller.scrollTop=0; fireEvent.scroll(scroller);
  expect(pageChange).not.toHaveBeenCalled(); expect(extracted).not.toHaveBeenCalled();
  expect(JSON.parse(localStorage.getItem('pdf-reading:task:A')).top).toBe(735);
  view.rerender(<PdfViewer {...props} active/>);
  await waitFor(()=>expect(scroller.scrollTop).toBe(735));
  expect(state.jump).not.toHaveBeenCalled();
  expect(state.mounts).toBe(1);
  view.unmount();
  const restored=render(<PdfViewer {...props}/>);
  expect(state.viewer.defaultScale).toBe(1.4);
  await act(async()=>state.viewer.onDocumentLoad({doc:readyDoc}));
  await waitFor(()=>expect(screen.getByTestId('pdf-scroll').scrollTop).toBe(735));
  restored.rerender(<PdfViewer {...props} readingKey="task:B"/>);
  expect(localStorage.getItem('pdf-reading:task:B')).toBeNull();
});

it('honors an explicit evidence jump on a newly opened paper over its old reading offset', async () => {
  localStorage.setItem('pdf-reading:task:A', JSON.stringify({ scale: 1.25, top: 735, left: 0 }));
  state.jump.mockImplementation(() => { screen.getByTestId('pdf-scroll').scrollTop = 300; });
  render(<PdfViewer fileUrl="A.pdf" pdfId="A" readingKey="task:A" targetPageIndex={1} targetPageJumpToken={100} />);
  await act(async () => state.viewer.onDocumentLoad({ doc: readyDoc }));
  expect(state.jump).toHaveBeenCalledWith(1);
  expect(screen.getByLabelText('原文缩放比例')).toHaveTextContent('125%');
  await act(async () => {});
  expect(screen.getByTestId('pdf-scroll').scrollTop).toBe(300);
});
