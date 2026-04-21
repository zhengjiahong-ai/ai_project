import { buildTranslationRequestPageLayout } from './pdfTranslationLayout.js';
import { createEmptyTranslationState, normalizeTranslationPage } from './translationState.js';

const VISUAL_ZONE_TYPES = new Set(['figure', 'table']);

const normalizeZoneType = (zone) => String(zone?.type || '').trim().toLowerCase();

export const shouldPreferPlainPageTranslation = ({ excludedZones = [], figureSnippets = [] } = {}) =>
  (Array.isArray(figureSnippets) && figureSnippets.length > 0) ||
  (Array.isArray(excludedZones) && excludedZones.some((zone) => VISUAL_ZONE_TYPES.has(normalizeZoneType(zone))));

export const preparePageTranslationRequest = ({
  pageText = '',
  pageLayout = null,
  excludedZones = [],
  preferPlain = false,
}) => {
  const sourceText = String(pageText || '').trim();
  const requestPageLayout = pageLayout
    ? buildTranslationRequestPageLayout(pageLayout, excludedZones, pageLayout?.excludedZonesVersion || 1)
    : null;
  const hasStructuredBlocks = Boolean(requestPageLayout?.blocks?.length);
  const shouldUseStructuredRequest = hasStructuredBlocks && !preferPlain;
  const translationSourceText = shouldUseStructuredRequest
    ? requestPageLayout.blocks.map((block) => block.text).join('\n\n').trim()
    : sourceText;

  return {
    sourceText,
    requestPageLayout,
    requestPayloadPageLayout: shouldUseStructuredRequest ? requestPageLayout : null,
    hasStructuredBlocks,
    requestMode: shouldUseStructuredRequest ? 'structured' : 'plain',
    translationSourceText,
    shouldMarkEmpty: !sourceText,
  };
};

export const planPageTranslationState = ({
  translationState,
  pdfId,
  pageIndex,
  sourceText = '',
  pageLayout = null,
  backgroundImage = '',
  figureSnippets = [],
  excludedZones = [],
  force = false,
  expectsStructuredResponse = false,
  shouldMarkEmpty = false,
  hasActiveRequest = false,
}) => {
  const baseState = translationState?.pdfId === pdfId ? translationState : createEmptyTranslationState(pdfId);
  const existingPage = normalizeTranslationPage(baseState.pages?.[pageIndex] || {});
  const createNextState = (pageValue) => ({
    ...baseState,
    currentPage: pageIndex,
    pages: {
      ...baseState.pages,
      [pageIndex]: normalizeTranslationPage(pageValue),
    },
  });

  if (shouldMarkEmpty) {
    return {
      shouldRequest: false,
      nextState: createNextState({
        sourceText: '',
        translatedText: '',
        translatedBlocks: [],
        renderMode: 'plain',
        pageLayout,
        backgroundImage,
        figureSnippets,
        excludedZones,
        status: 'empty',
        error: '当前页未提取到可翻译文本，可能是扫描页或图片页。',
        updatedAt: Date.now(),
      }),
    };
  }

  const isCacheHit =
    !force &&
    existingPage.sourceText === sourceText &&
    existingPage.status === 'success' &&
    existingPage.translatedText &&
    (!expectsStructuredResponse || existingPage.renderMode === 'overlay');

  const isActiveLoading =
    !force &&
    existingPage.sourceText === sourceText &&
    existingPage.status === 'loading' &&
    hasActiveRequest;

  if (isCacheHit || isActiveLoading) {
    return {
      shouldRequest: false,
      nextState: baseState.currentPage === pageIndex ? baseState : { ...baseState, currentPage: pageIndex },
    };
  }

  return {
    shouldRequest: true,
    nextState: createNextState({
      ...existingPage,
      sourceText,
      translatedText: existingPage.sourceText === sourceText && !force ? existingPage.translatedText || '' : '',
      translatedBlocks: existingPage.sourceText === sourceText && !force ? existingPage.translatedBlocks || [] : [],
      renderMode: existingPage.renderMode || 'plain',
      pageLayout: pageLayout || existingPage.pageLayout || null,
      backgroundImage: backgroundImage || existingPage.backgroundImage || '',
      figureSnippets: figureSnippets.length > 0 ? figureSnippets : existingPage.figureSnippets || [],
      excludedZones: excludedZones.length > 0 ? excludedZones : existingPage.excludedZones || [],
      status: 'loading',
      error: '',
      updatedAt: Date.now(),
    }),
  };
};
