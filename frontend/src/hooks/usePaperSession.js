import { useCallback } from 'react';

import { initDB } from '../services/localDb.js';
import {
  createReadyMessages,
  loadLibraryEntries,
  loadPaperSnapshot,
  normalizeHistoryMessages,
  persistStoredLastPdfId,
  readStoredActiveTab,
  readStoredLastPdfId,
  resolveStoredPdfRecord,
} from '../services/workspaceSession.js';

export const usePaperSession = ({
  apiService,
  defaultActiveTab,
  normalizeBackgroundKnowledgeLevel,
  normalizeBackgroundReaderProfile,
  normalizeSocraticSession,
  normalizeTranslationState,
  setPdfId,
  setPdfFile,
  setPdfFileName,
  setDeconstructData,
  setNotes,
  setAnalysisData,
  setBackgroundKnowledgeData,
  setBackgroundReaderProfile,
  setMessages,
  setPdfHighlights,
  setWorkbenchCards,
  setSocraticSession,
  commitTranslationState,
  setIsTranslated,
  currentPageTextRef,
  setPdfPageState,
  jumpToPage,
  setTargetPageIndex,
  setActiveTab,
  lastNonTranslationTabRef,
  setPapersList,
  setIsRestored,
  setTaskActive,
  papersListRef,
}) => {
  const fetchRemoteHistory = useCallback(async (sessionId, fallbackMessages = []) => {
    try {
      const response = await apiService.getChatHistory(sessionId);
      const remoteMessages = normalizeHistoryMessages(response?.messages || []);
      if (remoteMessages.length > 0) {
        const db = await initDB();
        await db.put('historyStore', remoteMessages, sessionId);
        return remoteMessages;
      }
    } catch (error) {
      console.warn('Failed to load remote chat history, using local cache instead.', error);
    }

    return fallbackMessages;
  }, [apiService]);

  const restorePaperState = useCallback(async (targetPdfId, entryList = null) => {
    const db = await initDB();
    const {
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
    } = await loadPaperSnapshot(db, targetPdfId);

    const resolvedPdf = resolveStoredPdfRecord(savedPdf);
    if (!resolvedPdf) {
      return false;
    }

    const currentEntries = Array.isArray(entryList) ? entryList : papersListRef.current;
    const libraryEntry = currentEntries.find((paper) => paper.id === targetPdfId);
    const savedPageIndex = Number.isFinite(libraryEntry?.currentPage)
      ? Math.max(0, libraryEntry.currentPage - 1)
      : 0;
    const savedTotalPages = Number.isFinite(libraryEntry?.totalPages)
      ? Math.max(0, libraryEntry.totalPages)
      : 0;
    const fallbackMessages =
      savedMessages && savedMessages.length > 0
        ? savedMessages
        : createReadyMessages(libraryEntry?.filename ?? resolvedPdf.name ?? '褰撳墠璁烘枃');

    const nextMessages = await fetchRemoteHistory(targetPdfId, fallbackMessages);

    setPdfId(targetPdfId);
    setPdfFile(URL.createObjectURL(resolvedPdf.blob));
    setPdfFileName(libraryEntry?.filename ?? resolvedPdf.name ?? null);
    setDeconstructData(savedDeconstruct || null);
    setNotes(savedNotes || []);
    setAnalysisData(savedAnalysis || null);
    setBackgroundKnowledgeData(savedBackgroundKnowledge || null);
    setBackgroundReaderProfile(normalizeBackgroundReaderProfile(
      savedBackgroundKnowledge?.reader_profile || {
        user_knowledge_level: normalizeBackgroundKnowledgeLevel(savedBackgroundKnowledge?.user_knowledge_level),
      },
    ));
    setMessages(nextMessages);
    setPdfHighlights(savedHighlights || []);
    setWorkbenchCards(savedWorkbenchCards || []);
    setSocraticSession(normalizeSocraticSession(savedSocraticSession, targetPdfId));
    commitTranslationState(normalizeTranslationState(savedTranslationState, targetPdfId));
    setIsTranslated(false);
    currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
    setPdfPageState({ pageIndex: savedPageIndex, totalPages: savedTotalPages });
    if (savedPageIndex > 0) {
      jumpToPage(savedPageIndex);
    } else {
      setTargetPageIndex(null);
    }
    setActiveTab((currentTab) =>
      currentTab === 'translation' ? lastNonTranslationTabRef.current || defaultActiveTab : currentTab,
    );
    persistStoredLastPdfId(targetPdfId);

    return true;
  }, [
    commitTranslationState,
    currentPageTextRef,
    defaultActiveTab,
    fetchRemoteHistory,
    jumpToPage,
    lastNonTranslationTabRef,
    normalizeBackgroundKnowledgeLevel,
    normalizeBackgroundReaderProfile,
    normalizeSocraticSession,
    normalizeTranslationState,
    papersListRef,
    setActiveTab,
    setAnalysisData,
    setBackgroundKnowledgeData,
    setBackgroundReaderProfile,
    setDeconstructData,
    setIsTranslated,
    setMessages,
    setNotes,
    setPdfFile,
    setPdfFileName,
    setPdfHighlights,
    setPdfId,
    setPdfPageState,
    setSocraticSession,
    setTargetPageIndex,
    setWorkbenchCards,
  ]);

  const restoreLocalSession = useCallback(async () => {
    try {
      const savedTab = readStoredActiveTab();
      if (savedTab && savedTab !== 'translation') {
        setActiveTab(savedTab);
      }

      const db = await initDB();
      const sortedList = await loadLibraryEntries(db);
      setPapersList(sortedList);

      const savedPdfId = readStoredLastPdfId();
      if (savedPdfId) {
        const restored = await restorePaperState(savedPdfId, sortedList);
        if (!restored && sortedList.length > 0) {
          await restorePaperState(sortedList[0].id, sortedList);
        }
      } else if (sortedList.length > 0) {
        await restorePaperState(sortedList[0].id, sortedList);
      }
    } catch (error) {
      console.error('Failed to restore local session.', error);
    } finally {
      setIsRestored(true);
    }
  }, [restorePaperState, setActiveTab, setIsRestored, setPapersList]);

  const restoreSelectedPaper = useCallback(async (targetPdfId) => {
    setTaskActive('aiReady', false);
    try {
      await restorePaperState(targetPdfId);
    } catch (error) {
      console.error('Failed to load selected paper.', error);
    } finally {
      setTaskActive('aiReady', true);
    }
  }, [restorePaperState, setTaskActive]);

  return {
    restorePaperState,
    restoreLocalSession,
    restoreSelectedPaper,
    createReadyMessages,
  };
};
