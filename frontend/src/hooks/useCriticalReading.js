import { useCallback } from 'react';
import { initDB } from '../services/localDb.js';
import {
  getCriticalReadingErrorCode,
  formatCriticalReadingErrorMessage,
} from '../utils/appHelpers.js';

/**
 * Encapsulates the critical-reading analysis handler.
 */
export function useCriticalReading({
  apiService,
  pdfId,
  setActiveTab,
  setTaskActive,
  setAnalysisData,
  setPapersList,
  showWarning,
  showError,
}) {
  const handleStartAnalysis = useCallback(async () => {
    if (!pdfId) {
      if (typeof showWarning === 'function') { showWarning('请先上传 PDF 文件。'); }
      return;
    }

    setActiveTab('analysis');
    setTaskActive('analyzing', true);

    try {
      const response = await apiService.criticalReading(pdfId);
      const payload = response?.analysis ?? response;
      const isSuccess = response?.status === 'success' || payload?.status === 'success';
      if (!isSuccess) {
        const analysisError = new Error(response?.message || payload?.message || '批判性阅读失败');
        analysisError.code = response?.errorCode || payload?.errorCode || null;
        analysisError.payload = response || payload || null;
        throw analysisError;
      }

      setAnalysisData(payload);
      const db = await initDB();
      await db.put('analysisStore', payload, pdfId);
    } catch (error) {
      console.error('Failed to run critical reading.', error);
      const errorCode = getCriticalReadingErrorCode(error);
      const errorMessage = formatCriticalReadingErrorMessage(error);
      if (errorCode === 'paper_not_indexed' || errorCode === 'rag_index_unavailable') {
        try {
          const db = await initDB();
          const paper = await db.get('libraryStore', pdfId);
          if (paper) {
            const updatedPaper = {
              ...paper,
              parseStatus: '索引异常',
              ragIndexed: false,
              ragErrorCode: errorCode,
              indexMessage: errorMessage,
              updatedAt: Date.now(),
            };
            await db.put('libraryStore', updatedPaper);
            setPapersList((prev) => prev.map((item) => (item.id === pdfId ? updatedPaper : item)));
          }
        } catch (storeError) {
          console.error('Failed to mark paper index status.', storeError);
        }
      }
      if (typeof showError === 'function') { showError(errorMessage); }
    } finally {
      setTaskActive('analyzing', false);
    }
  }, [apiService, pdfId, setActiveTab, setTaskActive, setAnalysisData, setPapersList, showWarning, showError]);

  return { handleStartAnalysis };
}
