import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ExplanationPopup } from './PdfViewer';
import { selectionNote } from '../utils/selectionNote';

const highlight = { id: 1, sourceAnchorId: 'selection-A', text: '原文片段', actionId: 'explain', actionLabel: '解释',
  position: { pageIndex: 3, top: 0, left: 0, height: 0, width: 0 }, highlightAreas: [], isLoading: false,
  chatHistory: [{ role: 'user', content: '解释原文' }, { role: 'ai', content: '已完成的解释' }] };

it('preserves a failed note and closes only after a confirmed save', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('保存冲突')).mockResolvedValueOnce();
  const close = vi.fn();
  render(<ExplanationPopup highlight={highlight} onSaveNote={save} onClose={close} onDelete={vi.fn()} onSubAsk={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '存为笔记' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('保存冲突');
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByText('已完成的解释')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '存为笔记' }));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  const note = selectionNote(save.mock.calls[0][0], 'paper-A', 'note-A');
  expect(note.text).toContain('已完成的解释');
  expect(Number.isFinite(Date.parse(note.createdAt))).toBe(true);
  expect(note.sources[0]).toMatchObject({ pdfId: 'paper-A', pageIndex: 3, sourceId: 'selection-A', text: '原文片段' });
});

it('does not save the automatic side-note acknowledgement as academic content', () => {
  const note = selectionNote({ text: '自己选取的原文', sourceActionId: 'note', sourcePageIndex: 2,
    aiInterpretation: '已保存为边注，可继续补充自己的观察与问题。' }, 'A', 'N');
  expect(note.text).toBe('自己选取的原文');
  expect(note.sources[0].pageIndex).toBe(2);
});
