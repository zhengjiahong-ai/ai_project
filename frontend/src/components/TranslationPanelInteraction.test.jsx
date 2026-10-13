import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
vi.mock('./PanoramicTranslation',()=>({default:()=>null}));
import TranslationPanel from './TranslationPanel';
const pageData={status:'success',translatedText:'当前页译文'};
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

it('offers stop during automatic translation and explicit restart after stopping', () => {
  const stop = vi.fn(), retry = vi.fn();
  const view = render(<TranslationPanel pdfId="A" pageData={{status:'loading'}} onCancel={stop} onRetry={retry}/>);
  expect(screen.queryByRole('button', {name:'重试翻译'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'停止翻译'}));
  expect(stop).toHaveBeenCalledTimes(1);
  view.rerender(<TranslationPanel pdfId="A" pageData={{status:'cancelled'}} onCancel={stop} onRetry={retry}/>);
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name:'继续翻译'}));
  expect(retry).toHaveBeenCalledTimes(1);
});

it('awaits saving, prevents duplicate clicks and opens the saved artifact', async()=>{
  const pending=deferred(), save=vi.fn(()=>pending.promise), open=vi.fn();
  const view=render(<TranslationPanel pdfId="A" pageData={pageData} onCaptureArtifact={save} onOpenArtifact={open}/>);
  fireEvent.click(screen.getByRole('button',{name:'保存译文'}));
  expect(screen.getByRole('button',{name:'保存中…'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'保存中…'}));
  expect(save).toHaveBeenCalledTimes(1);
  expect(save.mock.calls[0][0]).toEqual(expect.objectContaining({pdfId:'A',kind:'translation-page',pageIndex:0}));
  await act(async()=>pending.resolve({artifactId:'saved-1'}));
  fireEvent.click(screen.getByRole('button',{name:'打开成果'}));
  expect(open).toHaveBeenCalledWith('saved-1');
  expect(save).toHaveBeenCalledTimes(1);
  view.rerender(<TranslationPanel pdfId="A" currentPage={1} pageData={pageData} onCaptureArtifact={save}/>);
  expect(screen.getByRole('button',{name:'保存译文'})).toBeEnabled();
});

it('isolates late saves and shows local errors without losing the translation', async()=>{
  const pending=deferred(), save=vi.fn(()=>pending.promise);
  const view=render(<TranslationPanel pdfId="A" pageData={pageData} onCaptureArtifact={save}/>);
  fireEvent.click(screen.getByRole('button',{name:'保存译文'}));
  view.rerender(<TranslationPanel pdfId="A" currentPage={1} pageData={pageData} onCaptureArtifact={save}/>);
  await act(async()=>pending.resolve({artifactId:'old-page'}));
  expect(screen.getByRole('button',{name:'保存译文'})).toBeEnabled();
  save.mockRejectedValueOnce(new Error('无法保存'));
  fireEvent.click(screen.getByRole('button',{name:'保存译文'}));
  await act(async()=>{});
  expect(screen.getByRole('alert')).toHaveTextContent('无法保存');
  expect(screen.getByText('当前页译文')).toBeInTheDocument();
});

it('uses the parent saved identity and places successful retries under more actions',()=>{
  const open=vi.fn(), retry=vi.fn();
  const view=render(<TranslationPanel pdfId="A" pageData={pageData} savedArtifactId="saved" onCaptureArtifact={vi.fn()} onOpenArtifact={open} onRetry={retry}/>);
  fireEvent.click(screen.getByRole('button',{name:'打开成果'}));
  expect(open).toHaveBeenCalledWith('saved');
  expect(screen.queryByRole('button',{name:'重试翻译'})).not.toBeInTheDocument();
  expect(screen.getByText('更多操作').closest('details')).not.toHaveAttribute('open');
  fireEvent.click(screen.getByText('更多操作'));
  fireEvent.click(screen.getByRole('button',{name:'重新生成译文'}));
  expect(retry).toHaveBeenCalledTimes(1);
  view.rerender(<TranslationPanel pdfId="A" pageData={{status:'error'}} onRetry={retry}/>);
  expect(screen.getByRole('button',{name:'重试翻译'})).toBeEnabled();
});
