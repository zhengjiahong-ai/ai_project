import { initDB } from './localDb';

const STORE_NAME = 'highlightStore';

/**
 * Load all highlights for a given PDF from IndexedDB.
 * @param {string} pdfId
 * @returns {Promise<Array>}
 */
export async function loadHighlights(pdfId) {
  const db = await initDB();
  const raw = await db.get(STORE_NAME, pdfId);
  return raw || [];
}

/**
 * Save all highlights for a given PDF to IndexedDB.
 * @param {string} pdfId
 * @param {Array} highlights - array of highlight objects
 */
export async function saveHighlights(pdfId, highlights) {
  const db = await initDB();
  await db.put(STORE_NAME, highlights, pdfId);
}

/**
 * Add a single highlight for a given PDF.
 * Reads existing highlights, appends the new one, saves back.
 * @param {string} pdfId
 * @param {Object} highlight - { id, pageIndex, color, text, createdAt, highlightAreas, ... }
 */
export async function addHighlight(pdfId, highlight) {
  const existing = await loadHighlights(pdfId);
  existing.push(highlight);
  await saveHighlights(pdfId, existing);
}

/**
 * Delete a single highlight by id.
 * @param {string} pdfId
 * @param {number|string} highlightId
 */
export async function deleteHighlight(pdfId, highlightId) {
  const existing = await loadHighlights(pdfId);
  const filtered = existing.filter((h) => h.id !== highlightId);
  await saveHighlights(pdfId, filtered);
}

/**
 * Get all highlights for a given PDF (alias for loadHighlights).
 * @param {string} pdfId
 * @returns {Promise<Array>}
 */
export async function getHighlights(pdfId) {
  return loadHighlights(pdfId);
}

export default {
  loadHighlights,
  saveHighlights,
  addHighlight,
  deleteHighlight,
  getHighlights,
};
