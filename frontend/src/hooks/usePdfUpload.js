import { useCallback } from 'react';
import { initDB } from '../services/localDb.js';
import { persistUploadedPaperSession, persistStoredLastPdfId } from '../services/workspaceSession.js';
import {
  buildStudyProgressSnapshot,
} from '../utils/studyProgress.js';
import {
  createEmptySocraticSession,
} from '../utils/socraticSessionModel.js';
import {
  createEmptyTranslationState,
} from '../utils/translationState.js';
import {
  createEmptyDeepResearchState,
} from '../components/deepResearchPanelModel.js';
import {
  normalizeAuthors,
  formatUploadErrorMessage,
} from '../utils/appHelpers.js';

const DEFAULT_BACKGROUND_READER_PROFILE = {
  selfAssessedFamiliarity: 'beginner',
  preferredDepth: '标准',
  learningGoal: '',
  knownConcepts: [],
  confusingConcepts: [],
};

/**
 * Encapsulates PDF upload logic and the handlePdfUpload handler.
 *
 * @param {object}   opts
 * @param {object}   opts.apiService
 * @param {Function} opts.createReadyMessages
 * @param {Function} opts.resetArtifacts
 * @param {Function} opts.resetPageNavigation
 * @param {Function} opts.setTaskActive
 * @param {Function} opts.commitTranslationState
 * @param {Function} opts.setPdfFileName
 * @param {Function} opts.setPdfFile
 * @param {Function} opts.setPdfId
 * @param {Function} opts.setDeconstructData
 * @param {Function} opts.setAnalysisData
 * @param {Function} opts.setBackgroundKnowledgeData
 * @param {Function} opts.setBackgroundReaderProfile
 * @param {Function} opts.setMessages
 * @param {Function} opts.setSocraticSession
 * @param {Function} opts.setIsTranslated
 * @param {Function} opts.setActiveTab
 * @param {Function} opts.setPapersList
 * @param {object}   opts.currentPageTextRef
 */
export function usePdfUpload({
  apiService,
  createReadyMessages,
  resetArtifacts,
  resetPageNavigation,
  setTaskActive,
  commitTranslationState,
  setPdfFileName,
  setPdfFile,
  setPdfId,
  setDeconstructData,
  setAnalysisData,
  setBackgroundKnowledgeData,
  setBackgroundReaderProfile,
  setMessages,
  setSocraticSession,
  setIsTranslated,
  setActiveTab,
  setPapersList,
  currentPageTextRef,
  showWarning,
  showError,
}) {
  const handlePdfUpload = useCallback(async (file) => {
    if (!file) return;

    setPdfFileName(file.name);
    setPdfFile(URL.createObjectURL(file));
    setTaskActive('aiReady', false);
    setTaskActive('deconstructing', true);

    try {
      const response = await apiService.uploadPdf(file);
      if (!response || response.status !== 'success') {
        throw new Error(response?.message || '论文上传失败');
      }

      const readyMessages = createReadyMessages(file.name);
      const initialStudyProgress = buildStudyProgressSnapshot({
        pdfId: response.pdfId,
        pdfPageState: { pageIndex: 0, totalPages: 0 },
        deconstructData: response,
        analysisData: null,
        backgroundKnowledgeData: null,
        socraticSession: createEmptySocraticSession(response.pdfId),
        translationState: createEmptyTranslationState(response.pdfId),
        messages: readyMessages,
        notes: [],
        pdfHighlights: [],
        workbenchCards: [],
        deepResearchState: createEmptyDeepResearchState(),
      });
      const newEntry = {
        id: response.pdfId,
        title: response.title || file.name,
        filename: file.name,
        authors: normalizeAuthors(response.authors),
        parseStatus: response.parseStatus || (response.ragIndexed === false ? '索引异常' : '已解析'),
        parseMessage: response.parseMessage || null,
        ragIndexed: response.ragIndexed !== false,
        ragChunkCount: response.ragChunkCount || 0,
        ragErrorCode: response.ragErrorCode || null,
        indexMessage: response.message || null,
        sectionCount: response.paper_structure?.sections?.length || 0,
        readingProgress: initialStudyProgress.readingProgress,
        currentPage: initialStudyProgress.currentPage,
        totalPages: initialStudyProgress.totalPages,
        studyProgress: initialStudyProgress.studyProgress,
        studyPhase: initialStudyProgress.studyPhase,
        studySummary: initialStudyProgress.studySummary,
        progressSignals: initialStudyProgress.progressSignals,
        timestamp: Date.now(),
        updatedAt: Date.now(),
      };

      const db = await initDB();
      await persistUploadedPaperSession({
        db,
        file,
        pdfId: response.pdfId,
        response,
        readyMessages,
        libraryEntry: newEntry,
      });

      setPdfId(response.pdfId);
      setDeconstructData(response);
      setAnalysisData(null);
      setBackgroundKnowledgeData(null);
      setBackgroundReaderProfile(DEFAULT_BACKGROUND_READER_PROFILE);
      resetArtifacts();
      setMessages(readyMessages);
      setSocraticSession(createEmptySocraticSession(response.pdfId));
      commitTranslationState(createEmptyTranslationState(response.pdfId));
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      resetPageNavigation();
      setActiveTab('deconstruct');
      setPapersList((prev) => [newEntry, ...prev.filter((paper) => paper.id !== response.pdfId)]);
      persistStoredLastPdfId(response.pdfId);

      if (response?.ragIndexed === false && response?.message) {
        if (typeof showWarning === 'function') { showWarning(response.message); }
      }
    } catch (error) {
      console.error('Failed to upload PDF.', error);
      setPdfFile(null);
      setPdfFileName(null);
      setPdfId(null);
      setSocraticSession(createEmptySocraticSession());
      setBackgroundKnowledgeData(null);
      setBackgroundReaderProfile(DEFAULT_BACKGROUND_READER_PROFILE);
      commitTranslationState(createEmptyTranslationState());
      setIsTranslated(false);
      currentPageTextRef.current = { pageIndex: 0, pageText: '', pageLayout: null };
      resetArtifacts();
      resetPageNavigation();
      const uploadErrorMessage = formatUploadErrorMessage(error);
      window.setTimeout(() => {
        if (typeof showError === 'function') { showError(uploadErrorMessage); }
      }, 0);
    } finally {
      setTaskActive('aiReady', true);
      setTaskActive('deconstructing', false);
    }
  }, [
    commitTranslationState,
    createReadyMessages,
    resetArtifacts,
    resetPageNavigation,
    setTaskActive,
    apiService,
    setPdfFileName,
    setPdfFile,
    setPdfId,
    setDeconstructData,
    setAnalysisData,
    setBackgroundKnowledgeData,
    setBackgroundReaderProfile,
    setMessages,
    setSocraticSession,
    setIsTranslated,
    setActiveTab,
    setPapersList,
    currentPageTextRef,
    showWarning,
    showError,
  ]);

  return { handlePdfUpload };
}
