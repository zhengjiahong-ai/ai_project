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

// ── Bookmarks ─────────────────────────────────────────────────────

/**
 * Get bookmarks for a PDF.
 * Bookmarks are stored as: { pdfId, bookmarks: [{pageIndex, label, createdAt}] }
 * @param {string} pdfId
 * @returns {Promise<Array>}
 */
export async function getBookmarks(pdfId) {
  const db = await initDB();
  const raw = await db.get(STORE_NAME, `bookmarks_${pdfId}`);
  return raw?.bookmarks || [];
}

/**
 * Toggle bookmark for a page. Removes if exists, adds if not.
 * @param {string} pdfId
 * @param {number} pageIndex
 * @param {string} label
 * @returns {Promise<Array>}
 */
export async function toggleBookmark(pdfId, pageIndex, label) {
  const bookmarks = await getBookmarks(pdfId);
  const existing = bookmarks.findIndex((b) => b.pageIndex === pageIndex);
  if (existing >= 0) {
    bookmarks.splice(existing, 1);
  } else {
    bookmarks.push({ pageIndex, label: label || `Page ${pageIndex + 1}`, createdAt: new Date().toISOString() });
  }
  const db = await initDB();
  await db.put(STORE_NAME, { pdfId, bookmarks }, `bookmarks_${pdfId}`);
  return bookmarks;
}

// ── Reading Progress ──────────────────────────────────────────────

/**
 * Save reading progress.
 * Progress is stored as: { pdfId, pageIndex, timestamp }
 * @param {string} pdfId
 * @param {number} pageIndex
 */
export async function saveProgress(pdfId, pageIndex) {
  const db = await initDB();
  await db.put(STORE_NAME, { pdfId, pageIndex, timestamp: new Date().toISOString() }, `progress_${pdfId}`);
}

/**
 * Get saved reading progress.
 * @param {string} pdfId
 * @returns {Promise<Object|null>}
 */
export async function getProgress(pdfId) {
  const db = await initDB();
  return await db.get(STORE_NAME, `progress_${pdfId}`) || null;
}

export default {
  loadHighlights,
  saveHighlights,
  addHighlight,
  deleteHighlight,
  getHighlights,
  getBookmarks,
  toggleBookmark,
  saveProgress,
  getProgress,
};
