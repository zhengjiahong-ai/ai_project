const { test, expect } = require('@playwright/test');

test.describe('PDF Annotation', () => {
  test('highlight store exports all required functions', async () => {
    const { loadHighlights, saveHighlights, addHighlight, deleteHighlight } = require('../../src/services/highlightStore.js');
    expect(typeof loadHighlights).toBe('function');
    expect(typeof saveHighlights).toBe('function');
    expect(typeof addHighlight).toBe('function');
    expect(typeof deleteHighlight).toBe('function');
  });

  test('notes store exports all required functions', async () => {
    const { loadNotes, saveNotes, upsertNote, deleteNote } = require('../../src/services/notesStore.js');
    expect(typeof loadNotes).toBe('function');
    expect(typeof saveNotes).toBe('function');
    expect(typeof upsertNote).toBe('function');
    expect(typeof deleteNote).toBe('function');
  });
});
