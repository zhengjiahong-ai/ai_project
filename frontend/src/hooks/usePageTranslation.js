import { useCallback, useRef } from 'react';
import {
  createEmptyTranslationState,
  normalizeTranslationPage,
} from '../utils/translationState.js';

const STRUCTURED_TRANSLATION_TIMEOUT_MS = 90000;

/**
 * Encapsulates page translation logic: request, page change handling,
 * text extraction, and retry.
 */
export function usePageTranslation({
  apiService,
  pdfId,
  deconstructData,
  commitTranslationState,
  setPdfPageState,
  pdfPageState,
  isTranslated,
  currentPageTextRef,
}) {
  const translationRequestsRef = useRef({});
  const translationRequestSequenceRef = useRef(0);
  const latestTranslationTokensRef = useRef({});

  const requestPageTranslation = useCallback(async ({
    pageIndex,
    pageText: sourceText,
    pageLayout = null,
    force = false,
  }) => {
    if (!pdfId) return;

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

    const previousRequest = translationRequestsRef.current[pageIndex];
    if (previousRequest?.controller) {
      previousRequest.controller.abort();
    }

    const requestToken = ++translationRequestSequenceRef.current;
    latestTranslationTokensRef.current[pageIndex] = requestToken;
    const isCurrentRequest = () => latestTranslationTokensRef.current[pageIndex] === requestToken;

    const runTranslateRequest = async (requestText, requestLayout, timeoutMs = 90000) => {
      const controller = new AbortController();
      translationRequestsRef.current[pageIndex] = { token: requestToken, controller };
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

      let response;
      if (expectsStructuredResponse) {
        try {
          response = await runTranslateRequest(
            sourceText, pageLayout, STRUCTURED_TRANSLATION_TIMEOUT_MS,
          );
        } catch {
          if (!isCurrentRequest()) return;
          response = await runTranslateRequest(sourceText, null);
        }
      } else {
        response = await runTranslateRequest(sourceText, pageLayout);
      }

      if (!isCurrentRequest()) return;

      const translatedText = response?.translatedText ?? response?.data?.translatedText ?? '';
      const translatedBlocks = Array.isArray(response?.translatedBlocks) ? response.translatedBlocks : [];
      const renderMode =
        response?.renderMode ||
        (translatedBlocks.length > 0 && pageLayout?.blocks?.length ? 'overlay' : 'plain');

      commitTranslationState((prev) => {
        if (prev?.pdfId !== pdfId || !isCurrentRequest()) return prev;
        return {
          ...prev,
          currentPage: pageIndex,
          pages: {
            ...prev.pages,
            [pageIndex]: normalizeTranslationPage({
              ...prev.pages?.[pageIndex],
              sourceText,
              translatedBlocks,
              renderMode,
              pageLayout: pageLayout || prev.pages?.[pageIndex]?.pageLayout || null,
              translatedText: translatedText || '暂无译文',
              status: 'success',
              error: '',
              updatedAt: Date.now(),
            }),
          },
        };
      });
    } catch (error) {
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
            pageLayout: pageLayout || existingPage.pageLayout || null,
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

    requestPageTranslation({ ...pagePayload, force: true });
  }, [requestPageTranslation, currentPageTextRef]);

  return {
    requestPageTranslation,
    handlePdfPageChange,
    handlePageTextExtracted,
    handleRetryTranslation,
  };
}
