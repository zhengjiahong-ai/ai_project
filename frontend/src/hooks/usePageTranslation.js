import { useCallback, useEffect, useRef } from 'react';
import {
  createEmptyTranslationState,
  normalizeTranslationPage,
} from '../utils/translationState.js';
import { buildTranslationRequestPageLayout } from '../utils/pdfTranslationLayout.js';

const STRUCTURED_TRANSLATION_TIMEOUT_MS = 90000;

/**
 * Encapsulates page translation logic: request, page change handling,
 * text extraction, and retry.
 */
export function usePageTranslation({
  apiService,
  pdfId,
  deconstructData,
  translationState,
  commitTranslationState,
  setPdfPageState,
  pdfPageState,
  isTranslated,
  currentPageTextRef,
}) {
  const translationRequestsRef = useRef({});
  const translationRequestSequenceRef = useRef(0);
  const latestTranslationTokensRef = useRef({});
  const latestPdfIdRef = useRef(pdfId);
  const stateRef = useRef(translationState);
  latestPdfIdRef.current = pdfId;
  stateRef.current = translationState;
  useEffect(() => () => {
    for (const request of Object.values(translationRequestsRef.current)) {
      if (request.status === 'running') { request.status = 'error'; request.controller?.abort(); }
    }
  }, [pdfId]);

  const requestPageTranslation = useCallback(async ({
    pageIndex,
    pageText: sourceText,
    pageLayout = null,
    force = false,
  }) => {
    if (!pdfId) return;
    const key = JSON.stringify([pdfId, pageIndex]);
    const cached = stateRef.current?.pdfId === pdfId ? stateRef.current.pages?.[pageIndex] : null;
    const previousRequest = translationRequestsRef.current[key];
    if (!force && (['success', 'partial', 'error', 'cancelled', 'translating', 'empty'].includes(cached?.status) || previousRequest)) return;
    const excludedZones = deconstructData?.translationLayoutIndex?.[pageIndex]?.excludedZones || [];
    const requestLayout = pageLayout?.blocks?.length
      ? buildTranslationRequestPageLayout(pageLayout, excludedZones) : pageLayout;
    const hasOnlyPreservedContent = pageLayout?.blocks?.length > 0 && requestLayout.blocks.length === 0;
    if (!String(sourceText || '').trim() || hasOnlyPreservedContent) {
      commitTranslationState(prev => prev?.pdfId !== pdfId ? prev : { ...prev,
        pages: { ...prev.pages, [pageIndex]: normalizeTranslationPage({ ...prev.pages?.[pageIndex],
          sourceText, pageLayout, status: 'empty' }) } });
      return;
    }

    commitTranslationState((prev) => {
      if (!prev || prev.pdfId !== pdfId) return prev;
      const page = normalizeTranslationPage(prev.pages?.[pageIndex] || {});
      if (page.status === 'translating' && !force) return prev;
      return {
        ...prev,
        pages: {
          ...prev.pages,
          [pageIndex]: { ...page, status: 'translating', error: '' },
        },
      };
    });

    if (previousRequest?.controller) {
      previousRequest.controller.abort();
    }

    const requestToken = ++translationRequestSequenceRef.current;
    latestTranslationTokensRef.current[key] = requestToken;
    const controller = new AbortController();
    const isCurrentRequest = () => !controller.signal.aborted && latestPdfIdRef.current === pdfId && latestTranslationTokensRef.current[key] === requestToken;
    const request = { token: requestToken, controller, status: 'running' };
    translationRequestsRef.current[key] = request;

    const runTranslateRequest = async (requestText, requestLayout, timeoutMs = 90000) => {
      return apiService.translatePage(
        pdfId,
        pageIndex,
        requestText,
        deconstructData?.paper_skeleton || null,
        requestLayout,
        { timeoutMs, signal: controller.signal },
      );
    };

    try {
      const pageLayoutBlocks = pageLayout?.blocks?.length || 0;
      const expectsStructuredResponse = pageLayoutBlocks > 0;

      const response = await runTranslateRequest(sourceText, requestLayout,
        expectsStructuredResponse ? STRUCTURED_TRANSLATION_TIMEOUT_MS : 90000);

      if (!isCurrentRequest()) return;
      request.status = 'success';

      const translatedText = response?.translatedText ?? response?.data?.translatedText ?? '';
      const translatedBlocks = Array.isArray(response?.translatedBlocks) ? response.translatedBlocks : [];
      const renderMode =
        response?.renderMode ||
        (translatedBlocks.length > 0 && pageLayout?.blocks?.length ? 'overlay' : 'plain');

      commitTranslationState((prev) => {
        if (prev?.pdfId !== pdfId || !isCurrentRequest()) return prev;
        return {
          ...prev,
          // Completion can arrive after navigation. Only navigation/extraction
          // changes the selected page; this response updates its own cache entry.
          pages: {
            ...prev.pages,
            [pageIndex]: normalizeTranslationPage({
              ...prev.pages?.[pageIndex],
              sourceText,
              translatedBlocks,
              renderMode,
              pageLayout: pageLayout || prev.pages?.[pageIndex]?.pageLayout || null,
              translatedText: translatedText || '暂无译文',
              status: response?.status === 'partial' ? 'partial' : 'success',
              warning: response?.warning || '',
              mathProtectionVersion: response?.mathProtectionVersion,
              missingBlockIds: response?.missingBlockIds || [],
              error: '',
              updatedAt: Date.now(),
            }),
          },
        };
      });
    } catch (error) {
      request.status = 'error';
      if (error.name === 'CanceledError' || error.message === 'canceled') return;
      if (!isCurrentRequest()) return;

      commitTranslationState((prev) => {
        if (prev?.pdfId !== pdfId || !isCurrentRequest()) return prev;
        return {
          ...prev,
          pages: {
            ...prev.pages,
            [pageIndex]: normalizeTranslationPage({
              ...prev.pages?.[pageIndex],
              status: 'error',
              error: error?.response?.data?.message || error?.message || '翻译失败',
              updatedAt: Date.now(),
            }),
          },
        };
      });
    }
  }, [apiService, pdfId, deconstructData, commitTranslationState]);

  const handlePdfPageChange = useCallback((pageChange) => {
    const pageIndex =
      typeof pageChange === 'number'
        ? pageChange
        : Number.isFinite(pageChange?.pageIndex)
          ? pageChange.pageIndex
          : 0;
    const totalPages =
      typeof pageChange === 'object' && Number.isFinite(pageChange?.totalPages)
        ? pageChange.totalPages
        : pdfPageState.totalPages;

    setPdfPageState({ pageIndex, totalPages });
    currentPageTextRef.current = { pageIndex, pageText: '', pageLayout: null };
    commitTranslationState((prev) => {
      const baseState = prev?.pdfId === pdfId ? prev : createEmptyTranslationState(pdfId);
      return baseState.currentPage === pageIndex ? baseState : { ...baseState, currentPage: pageIndex };
    });
  }, [commitTranslationState, pdfId, pdfPageState.totalPages, setPdfPageState, currentPageTextRef]);

  const handlePageTextExtracted = useCallback(({
    pageIndex,
    pageText,
    pageLayout = null,
  }) => {
    const excludedZones = deconstructData?.translationLayoutIndex?.[pageIndex]?.excludedZones || [];
    currentPageTextRef.current = { pageIndex, pageText, pageLayout };
    commitTranslationState((prev) => {
      const baseState = prev?.pdfId === pdfId ? prev : createEmptyTranslationState(pdfId);
      const existingPage = normalizeTranslationPage(baseState.pages?.[pageIndex] || {});
      return {
        ...baseState,
        currentPage: pageIndex,
        pages: {
          ...baseState.pages,
          [pageIndex]: normalizeTranslationPage({
            ...existingPage,
            sourceText: pageText || existingPage.sourceText,
            // Cached block IDs belong to the layout used by their translation request.
            // A fresh parser pass may regroup paragraphs and assign different IDs.
            pageLayout: existingPage.translatedBlocks.length && existingPage.pageLayout
              ? existingPage.pageLayout : pageLayout || existingPage.pageLayout || null,
            excludedZones: excludedZones.length > 0 ? excludedZones : existingPage.excludedZones || [],
          }),
        },
      };
    });

    if (isTranslated) {
      requestPageTranslation({ pageIndex, pageText, pageLayout });
    }
  }, [commitTranslationState, deconstructData, isTranslated, pdfId, requestPageTranslation, currentPageTextRef]);

  const handleRetryTranslation = useCallback((translationState) => {
    const currentPage = translationState.currentPage ?? currentPageTextRef.current.pageIndex ?? 0;
    const pagePayload =
      currentPageTextRef.current.pageIndex === currentPage
        ? currentPageTextRef.current
        : {
            pageIndex: currentPage,
            pageText: translationState.pages?.[currentPage]?.sourceText || '',
            pageLayout: translationState.pages?.[currentPage]?.pageLayout || null,
          };

    return requestPageTranslation({ ...pagePayload, force: true });
  }, [requestPageTranslation, currentPageTextRef]);

  const handleCancelTranslation = useCallback((pageIndex = stateRef.current.currentPage) => {
    const request = translationRequestsRef.current[JSON.stringify([pdfId, pageIndex])];
    if (!request || request.status !== 'running') return;
    request.status = 'cancelled'; request.controller.abort();
    commitTranslationState(prev => prev?.pdfId !== pdfId ? prev : { ...prev, pages: { ...prev.pages,
      [pageIndex]: normalizeTranslationPage({ ...prev.pages[pageIndex],
        status: prev.pages[pageIndex]?.translatedText || prev.pages[pageIndex]?.translatedBlocks?.length ? 'partial' : 'cancelled',
        warning: '已停止翻译，已保存的译文仍保留。', error: '', updatedAt: Date.now() }) } });
  }, [pdfId, commitTranslationState]);

  return {
    requestPageTranslation,
    handlePdfPageChange,
    handlePageTextExtracted,
    handleRetryTranslation,
    handleCancelTranslation,
  };
}
