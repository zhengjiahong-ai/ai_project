import { initDB } from './localDb';

const STORE_NAME = 'notesStore';

/**
 * Load all notes for a given PDF.
 * @param {string} pdfId
 * @returns {Promise<Array<{id, pdfId, sectionId, pageIndex, content, createdAt, updatedAt}>>}
 */
export async function loadNotes(pdfId) {
  const db = await initDB();
  const raw = await db.get(STORE_NAME, pdfId);
  return raw || [];
}

/**
 * Save all notes for a given PDF.
 */
export async function saveNotes(pdfId, notes) {
  const db = await initDB();
  await db.put(STORE_NAME, notes, pdfId);
}

/**
 * Add or update a note. If note.id exists, replace it; otherwise append.
 */
export async function upsertNote(pdfId, note) {
  const notes = await loadNotes(pdfId);
  const idx = notes.findIndex((n) => n.id === note.id);
  if (idx >= 0) {
    notes[idx] = { ...note, updatedAt: new Date().toISOString() };
  } else {
    notes.push({
      ...note,
      id: note.id || `note-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
  }
  await saveNotes(pdfId, notes);
  return notes;
}

/**
 * Delete a note by id.
 */
export async function deleteNote(pdfId, noteId) {
  const notes = await loadNotes(pdfId);
  const filtered = notes.filter((n) => n.id !== noteId);
  await saveNotes(pdfId, filtered);
  return filtered;
}

export default { loadNotes, saveNotes, upsertNote, deleteNote };
