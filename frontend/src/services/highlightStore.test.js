import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  loadHighlights,
  addHighlight,
  deleteHighlight,
  getBookmarks,
  toggleBookmark,
  getHighlights,
  saveHighlights,
  saveProgress,
  getProgress,
} from './highlightStore.js';

// Mock localDb
const mockDb = {
  get: vi.fn(),
  put: vi.fn(),
};

vi.mock('./localDb', () => ({
  initDB: vi.fn(() => Promise.resolve(mockDb)),
}));

describe('highlightStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loadHighlights returns empty array when no data stored', async () => {
    mockDb.get.mockResolvedValue(undefined);
    const result = await loadHighlights('pdf-1');
    expect(result).toEqual([]);
    expect(mockDb.get).toHaveBeenCalledWith('highlightStore', 'pdf-1');
  });

  it('loadHighlights returns saved highlights array', async () => {
    const highlights = [{ id: 1, text: 'Important finding', pageIndex: 0 }];
    mockDb.get.mockResolvedValue(highlights);
    const result = await loadHighlights('pdf-1');
    expect(result).toEqual(highlights);
  });

  it('addHighlight appends new highlight to existing ones', async () => {
    const existing = [{ id: 1, text: 'First highlight' }];
    mockDb.get.mockResolvedValue(existing);
    mockDb.put.mockResolvedValue(undefined);

    await addHighlight('pdf-1', { id: 2, text: 'Second highlight', pageIndex: 1 });

    expect(mockDb.put).toHaveBeenCalledWith(
      'highlightStore',
      [
        { id: 1, text: 'First highlight' },
        { id: 2, text: 'Second highlight', pageIndex: 1 },
      ],
      'pdf-1',
    );
  });

  it('deleteHighlight removes highlight by id', async () => {
    mockDb.get.mockResolvedValue([
      { id: 1, text: 'Keep me' },
      { id: 2, text: 'Remove me' },
    ]);
    mockDb.put.mockResolvedValue(undefined);

    await deleteHighlight('pdf-1', 2);

    expect(mockDb.put).toHaveBeenCalledWith(
      'highlightStore',
      [{ id: 1, text: 'Keep me' }],
      'pdf-1',
    );
  });

  it('getHighlights is an alias for loadHighlights', async () => {
    const highlights = [{ id: 1, text: 'test' }];
    mockDb.get.mockResolvedValue(highlights);
    const result = await getHighlights('pdf-1');
    expect(result).toEqual(highlights);
    expect(mockDb.get).toHaveBeenCalledWith('highlightStore', 'pdf-1');
  });

  it('getBookmarks returns empty array when no bookmarks stored', async () => {
    mockDb.get.mockResolvedValue(undefined);
    const result = await getBookmarks('pdf-1');
    expect(result).toEqual([]);
  });

  it('toggleBookmark adds bookmark when it does not already exist', async () => {
    mockDb.get.mockResolvedValue(undefined);
    mockDb.put.mockResolvedValue(undefined);

    const result = await toggleBookmark('pdf-1', 0, 'Page 1');

    expect(result).toHaveLength(1);
    expect(result[0].pageIndex).toBe(0);
    expect(result[0].label).toBe('Page 1');
  });

  it('toggleBookmark removes bookmark when it already exists', async () => {
    mockDb.get.mockResolvedValue({
      pdfId: 'pdf-1',
      bookmarks: [{ pageIndex: 0, label: 'Page 1', createdAt: '2026-01-01T00:00:00.000Z' }],
    });
    mockDb.put.mockResolvedValue(undefined);

    const result = await toggleBookmark('pdf-1', 0, 'Page 1');

    expect(result).toHaveLength(0);
  });

  it('saveProgress stores reading progress for a pdf', async () => {
    mockDb.put.mockResolvedValue(undefined);

    await saveProgress('pdf-1', 5);

    expect(mockDb.put).toHaveBeenCalledOnce();
    const callArg = mockDb.put.mock.calls[0];
    expect(callArg[0]).toBe('highlightStore');
    expect(callArg[1].pdfId).toBe('pdf-1');
    expect(callArg[1].pageIndex).toBe(5);
    expect(callArg[2]).toBe('progress_pdf-1');
  });

  it('getProgress returns null when no progress saved', async () => {
    mockDb.get.mockResolvedValue(undefined);
    const result = await getProgress('pdf-1');
    expect(result).toBeNull();
  });

  it('addHighlight works when no existing highlights', async () => {
    mockDb.get.mockResolvedValue(undefined);
    mockDb.put.mockResolvedValue(undefined);

    await addHighlight('pdf-1', { id: 1, text: 'First ever highlight' });

    expect(mockDb.put).toHaveBeenCalledWith(
      'highlightStore',
      [{ id: 1, text: 'First ever highlight' }],
      'pdf-1',
    );
  });
});
