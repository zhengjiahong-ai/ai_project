import { openDB } from 'idb';

export const LOCAL_DB_NAME = 'PixiuAcademicDB_v6';
export const LOCAL_DB_VERSION = 6;

export const PAPER_SCOPED_STORES = [
  'pdfStore',
  'historyStore',
  'analysisStore',
  'notesStore',
  'deconstructStore',
  'highlightStore',
  'sessionStore',
  'translationStore',
  'backgroundKnowledgeStore',
  'artifactStore',
];

export const initDB = async () =>
  openDB(LOCAL_DB_NAME, LOCAL_DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('pdfStore')) db.createObjectStore('pdfStore');
      if (!db.objectStoreNames.contains('historyStore')) db.createObjectStore('historyStore');
      if (!db.objectStoreNames.contains('analysisStore')) db.createObjectStore('analysisStore');
      if (!db.objectStoreNames.contains('notesStore')) db.createObjectStore('notesStore');
      if (!db.objectStoreNames.contains('deconstructStore')) db.createObjectStore('deconstructStore');
      if (!db.objectStoreNames.contains('libraryStore')) db.createObjectStore('libraryStore', { keyPath: 'id' });
      if (!db.objectStoreNames.contains('highlightStore')) db.createObjectStore('highlightStore');
      if (!db.objectStoreNames.contains('sessionStore')) db.createObjectStore('sessionStore');
      if (!db.objectStoreNames.contains('translationStore')) db.createObjectStore('translationStore');
      if (!db.objectStoreNames.contains('backgroundKnowledgeStore')) db.createObjectStore('backgroundKnowledgeStore');
      if (!db.objectStoreNames.contains('artifactStore')) db.createObjectStore('artifactStore');
    },
  });

export const deletePaperScopedRecords = async (db, pdfId) =>
  Promise.all(PAPER_SCOPED_STORES.map((storeName) => db.delete(storeName, pdfId)));
