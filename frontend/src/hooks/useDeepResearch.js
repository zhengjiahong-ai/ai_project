import { useCallback } from 'react';
import {
  createEmptyDeepResearchState,
  normalizeResearchBriefPreview,
  normalizeResearchTask,
} from '../components/deepResearchPanelModel.js';

/**
 * Encapsulates Deep Research handlers: question input, brief preview,
 * task CRUD, plan/final review, and cancellation.
 */
export function useDeepResearch({
  apiService,
  pdfId,
  deconstructData,
  deepResearchStateByPdf,
  setDeepResearchStateForPdf,
  fetchDeepResearchTrace,
  currentPdfIdRef,
  setActiveTab,
}) {
  const handleDeepResearchQuestionChange = useCallback((nextQuestionDraft) => {
    if (!pdfId) return;
    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      questionDraft: nextQuestionDraft,
    }));
  }, [pdfId, setDeepResearchStateForPdf]);

  const handleDeepResearchBriefConstraintsChange = useCallback((nextConstraintsDraft) => {
    if (!pdfId) return;
    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      briefConstraintsDraft: nextConstraintsDraft,
    }));
  }, [pdfId, setDeepResearchStateForPdf]);

  const handlePreviewResearchBrief = useCallback(async () => {
    if (!pdfId) return;

    const currentState = deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState();
    const question = `${currentState.questionDraft || ''}`.trim();
    if (!question) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        briefError: '请输入研究问题后再生成研究 brief。',
      }));
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isPreviewingBrief: true,
      briefError: '',
      errorMessage: '',
    }));

    try {
      const response = await apiService.previewResearchBrief(
        question,
        pdfId,
        deconstructData?.paper_skeleton || null,
        currentState.briefConstraintsDraft || '',
      );
      const nextPreview = normalizeResearchBriefPreview(response?.briefPreview);
      if (response?.status !== 'success' || !nextPreview) {
        throw new Error(response?.message || '研究 brief 生成失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        questionDraft: question,
        briefPreview: nextPreview,
        briefError: '',
        isPreviewingBrief: false,
      }));
    } catch (error) {
      console.error('Failed to preview deep research brief.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        isPreviewingBrief: false,
        briefError: error?.response?.data?.message || error?.message || '研究 brief 生成失败，请稍后重试。',
      }));
    }
  }, [deepResearchStateByPdf, deconstructData, pdfId, setDeepResearchStateForPdf]);

  const handleStartResearchTask = useCallback(async ({ useBriefPreview = false } = {}) => {
    if (!pdfId) return;

    const currentState = deepResearchStateByPdf[pdfId] || createEmptyDeepResearchState();
    const question = `${currentState.questionDraft || ''}`.trim();
    if (!question) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        errorMessage: '请输入研究问题后再启动深度研究任务。',
      }));
      return;
    }

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isCreating: true,
      isCancelling: false,
      errorMessage: '',
      pollError: '',
      briefError: '',
    }));

    try {
      const response = await apiService.createResearchTask(
        question,
        pdfId,
        deconstructData?.paper_skeleton || null,
        useBriefPreview ? currentState.briefConstraintsDraft || '' : '',
        useBriefPreview ? currentState.briefPreview : null,
        Boolean(currentState.allowExternalSearch),
      );
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务创建失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        questionDraft: question,
        task: nextTask,
        errorMessage: '',
        pollError: '',
        isCreating: false,
        isCancelling: false,
        traceSummary: null,
        traceError: '',
        isTraceLoading: false,
      }));

      fetchDeepResearchTrace(pdfId, nextTask.traceId);

      if (currentPdfIdRef.current === pdfId) {
        setActiveTab('deep-research');
      }
    } catch (error) {
      console.error('Failed to create deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => ({
        ...prev,
        isCreating: false,
        errorMessage: error?.response?.data?.message || error?.message || '深度研究任务创建失败，请稍后重试。',
      }));
    }
  }, [deepResearchStateByPdf, deconstructData, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf, currentPdfIdRef, setActiveTab]);

  const handleRefreshResearchTask = useCallback(async () => {
    if (!pdfId) return;

    const currentTaskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!currentTaskId) return;

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      errorMessage: '',
      pollError: '',
    }));

    try {
      const response = await apiService.getResearchTask(currentTaskId);
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务状态刷新失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) return prev;
        return {
          ...prev,
          task: nextTask,
          errorMessage: '',
          pollError: '',
          isCreating: false,
          isCancelling: false,
        };
      });

      fetchDeepResearchTrace(pdfId, nextTask.traceId);
    } catch (error) {
      console.error('Failed to refresh deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) return prev;
        return {
          ...prev,
          pollError: error?.response?.data?.message || error?.message || '深度研究任务状态刷新失败。',
        };
      });
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const handleReviewResearchPlan = useCallback(async (payload) => {
    const taskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!pdfId || !taskId) return;
    try {
      const response = await apiService.reviewResearchPlan(taskId, payload);
      const task = normalizeResearchTask(response?.task);
      if (!task) throw new Error(response?.message || '计划确认失败');
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, task, errorMessage: '', pollError: '' }));
    } catch (error) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, errorMessage: error?.response?.data?.message || error?.message || '计划确认失败。' }));
    }
  }, [deepResearchStateByPdf, pdfId, setDeepResearchStateForPdf]);

  const handleReviewResearchFinal = useCallback(async (payload) => {
    const taskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!pdfId || !taskId) return;
    try {
      const response = await apiService.reviewResearchFinal(taskId, payload);
      const task = normalizeResearchTask(response?.task);
      if (!task) throw new Error(response?.message || '终稿确认失败');
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, task, errorMessage: '', pollError: '' }));
      fetchDeepResearchTrace(pdfId, task.traceId);
    } catch (error) {
      setDeepResearchStateForPdf(pdfId, (prev) => ({ ...prev, errorMessage: error?.response?.data?.message || error?.message || '终稿确认失败。' }));
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  const handleCancelResearchTask = useCallback(async () => {
    if (!pdfId) return;

    const currentTaskId = deepResearchStateByPdf[pdfId]?.task?.taskId;
    if (!currentTaskId) return;

    setDeepResearchStateForPdf(pdfId, (prev) => ({
      ...prev,
      isCancelling: true,
      errorMessage: '',
      pollError: '',
    }));

    try {
      const response = await apiService.cancelResearchTask(currentTaskId);
      const nextTask = normalizeResearchTask(response?.task);
      if (response?.status !== 'success' || !nextTask) {
        throw new Error(response?.message || '深度研究任务取消失败');
      }

      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) return prev;
        return {
          ...prev,
          task: nextTask,
          errorMessage: '',
          pollError: '',
          isCreating: false,
          isCancelling: false,
        };
      });

      fetchDeepResearchTrace(pdfId, nextTask.traceId);
    } catch (error) {
      console.error('Failed to cancel deep research task.', error);
      setDeepResearchStateForPdf(pdfId, (prev) => {
        if ((prev.task?.taskId || '') !== currentTaskId) return prev;
        return {
          ...prev,
          isCancelling: false,
          errorMessage: error?.response?.data?.message || error?.message || '深度研究任务取消失败。',
        };
      });
    }
  }, [deepResearchStateByPdf, fetchDeepResearchTrace, pdfId, setDeepResearchStateForPdf]);

  return {
    handleDeepResearchQuestionChange,
    handleDeepResearchBriefConstraintsChange,
    handlePreviewResearchBrief,
    handleStartResearchTask,
    handleRefreshResearchTask,
    handleReviewResearchPlan,
    handleReviewResearchFinal,
    handleCancelResearchTask,
  };
}
