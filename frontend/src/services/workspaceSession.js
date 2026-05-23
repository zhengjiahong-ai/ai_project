export const ACTIVE_TAB_STORAGE_KEY = 'activeTab';
export const LAST_PDF_ID_STORAGE_KEY = 'lastPdfId';

export const normalizeHistoryMessages = (messages = []) =>
  messages.map((message, index) => ({
    id: message.id ?? `${message.timestamp ?? 'local'}-${index}`,
    role: message.role === 'assistant' ? 'ai' : message.role,
    content: message.content,
    timestamp: message.timestamp ?? null,
  }));

export const createReadyMessages = (filename) => [
  {
    role: 'ai',
    content: `已成功加载论文：${filename}。我现在可以为您分析这篇文章了。`,
  },
];

export const loadLibraryEntries = async (db) => {
  const list = await db.getAll('libraryStore');
  return [...list].sort((left, right) => right.timestamp - left.timestamp);
};

export const loadPaperSnapshot = async (db, pdfId) => {
  const [
    savedPdf,
    savedMessages,
    savedAnalysis,
    savedDeconstruct,
    savedNotes,
    savedHighlights,
    savedSocraticSession,
    savedTranslationState,
    savedBackgroundKnowledge,
    savedWorkbenchCards,
  ] = await Promise.all([
    db.get('pdfStore', pdfId),
    db.get('historyStore', pdfId),
    db.get('analysisStore', pdfId),
    db.get('deconstructStore', pdfId),
    db.get('notesStore', pdfId),
    db.get('highlightStore', pdfId),
    db.get('sessionStore', pdfId),
    db.get('translationStore', pdfId),
    db.get('backgroundKnowledgeStore', pdfId),
    db.get('artifactStore', pdfId),
  ]);

  return {
    savedPdf,
    savedMessages,
    savedAnalysis,
    savedDeconstruct,
    savedNotes,
    savedHighlights,
    savedSocraticSession,
    savedTranslationState,
    savedBackgroundKnowledge,
    savedWorkbenchCards,
  };
};

export const persistUploadedPaperSession = async ({
  db,
  file,
  pdfId,
  response,
  readyMessages,
  libraryEntry,
}) =>
  Promise.all([
    db.put('pdfStore', file, pdfId),
    db.put('deconstructStore', response, pdfId),
    db.put('analysisStore', null, pdfId),
    db.put('historyStore', readyMessages, pdfId),
    db.put('highlightStore', [], pdfId),
    db.put('artifactStore', [], pdfId),
    db.put('libraryStore', libraryEntry),
    db.delete('sessionStore', pdfId),
    db.delete('translationStore', pdfId),
    db.delete('backgroundKnowledgeStore', pdfId),
  ]);

export const persistMessages = async (db, pdfId, messages) => {
  if (!pdfId || !messages || messages.length === 0) {
    return;
  }

  await db.put('historyStore', messages, pdfId);
};

export const persistNotes = async (db, pdfId, notes) => {
  if (!pdfId) {
    return;
  }

  await db.put('notesStore', notes, pdfId);
};

export const persistWorkbenchCards = async (db, pdfId, workbenchCards) => {
  if (!pdfId) {
    return;
  }

  await db.put('artifactStore', workbenchCards, pdfId);
};

export const persistSocraticSession = async (db, pdfId, socraticSession) => {
  if (!pdfId) {
    return;
  }

  const shouldPersist =
    socraticSession?.started
    || socraticSession?.isComplete
    || Boolean(`${socraticSession?.readingProgress || ''}`.trim());

  if (!shouldPersist) {
    await db.delete('sessionStore', pdfId);
    return;
  }

  await db.put(
    'sessionStore',
    {
      ...socraticSession,
      updatedAt: Date.now(),
    },
    pdfId,
  );
};

export const persistTranslationState = async (db, pdfId, translationState) => {
  if (!pdfId) {
    return;
  }

  await db.put(
    'translationStore',
    {
      ...translationState,
      updatedAt: Date.now(),
    },
    pdfId,
  );
};

export const persistLibraryReadingProgress = async (db, pdfId, readingProgressPayload) => {
  if (!pdfId) {
    return;
  }

  const paper = await db.get('libraryStore', pdfId);
  if (!paper) {
    return;
  }

  await db.put('libraryStore', {
    ...paper,
    ...readingProgressPayload,
  });
};

export const readStoredActiveTab = () => localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);

export const persistStoredActiveTab = (activeTab) => {
  localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
};

export const readStoredLastPdfId = () => localStorage.getItem(LAST_PDF_ID_STORAGE_KEY);

export const persistStoredLastPdfId = (pdfId) => {
  localStorage.setItem(LAST_PDF_ID_STORAGE_KEY, pdfId);
};

export const clearStoredLastPdfId = () => {
  localStorage.removeItem(LAST_PDF_ID_STORAGE_KEY);
};

export const resolveStoredPdfRecord = (storedValue) => {
  if (!storedValue) {
    return null;
  }

  if (storedValue instanceof Blob) {
    return {
      blob: storedValue,
      name: storedValue.name ?? null,
    };
  }

  if (storedValue.blob instanceof Blob) {
    return {
      blob: storedValue.blob,
      name: storedValue.name ?? storedValue.blob.name ?? null,
    };
  }

  return null;
};
