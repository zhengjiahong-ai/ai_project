/**
 * PDF Annotation E2E Tests (21-1, 21-2).
 */
import { expect, test } from '@playwright/test';

test.describe('PDF Annotation', () => {
  test('highlight store exports all required functions', async () => {
    const store = await import('../../src/services/highlightStore.js');
    expect(typeof store.loadHighlights).toBe('function');
    expect(typeof store.saveHighlights).toBe('function');
    expect(typeof store.addHighlight).toBe('function');
    expect(typeof store.deleteHighlight).toBe('function');
    expect(typeof store.getBookmarks).toBe('function');
    expect(typeof store.toggleBookmark).toBe('function');
    expect(typeof store.saveProgress).toBe('function');
    expect(typeof store.getProgress).toBe('function');
  });

  test('notes store exports all required functions', async () => {
    const store = await import('../../src/services/notesStore.js');
    expect(typeof store.loadNotes).toBe('function');
    expect(typeof store.saveNotes).toBe('function');
    expect(typeof store.upsertNote).toBe('function');
    expect(typeof store.deleteNote).toBe('function');
  });
});
