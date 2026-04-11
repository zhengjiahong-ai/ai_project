import {
  normalizeExcludedZones,
  normalizeFigureSnippets,
  normalizeRelativeBbox,
  normalizeViewport,
} from './pdfTranslationLayout.js';

const normalizePageLayout = (pageLayout) => {
  if (!pageLayout || !Array.isArray(pageLayout.blocks)) {
    return null;
  }

  const viewport = normalizeViewport(pageLayout.viewport || {});
  const orientation =
    pageLayout.orientation === 'landscape' || pageLayout.orientation === 'portrait'
      ? pageLayout.orientation
      : viewport.width > viewport.height
        ? 'landscape'
        : 'portrait';

  return {
    viewport,
    orientation,
    columnMode: pageLayout.columnMode === 'two-column' ? 'two-column' : 'single-column',
    blocks: pageLayout.blocks
      .map((block, index) => ({
        id: String(block?.id || `block-${index + 1}`),
        text: String(block?.text || ''),
        bbox: normalizeRelativeBbox(block?.bbox || {}),
        style: {
          fontSize: Number(Number(block?.style?.fontSize || 12).toFixed(2)),
          fontWeight: block?.style?.fontWeight === 'bold' ? 'bold' : 'normal',
          italic: Boolean(block?.style?.italic),
          textAlign: String(block?.style?.textAlign || 'left'),
        },
        readingOrder: Number.isFinite(Number(block?.readingOrder)) ? Number(block.readingOrder) : index,
      }))
      .filter((block) => block.id && block.bbox.width > 0 && block.bbox.height > 0),
  };
};

const normalizeTranslatedBlocks = (translatedBlocks = []) =>
  Array.isArray(translatedBlocks)
    ? translatedBlocks
        .map((block) => ({
          id: String(block?.id || '').trim(),
          translatedText: String(block?.translatedText || '').trim(),
        }))
        .filter((block) => block.id && block.translatedText)
    : [];

export const createEmptyTranslationState = (pdfId = null, overrides = {}) => ({
  pdfId,
  currentPage: 0,
  pages: {},
  updatedAt: null,
  ...overrides,
});

export const canRenderOverlay = (pageData = null) => {
  const pageLayout = pageData?.pageLayout;
  const hasStructuredText = Boolean(
    pageLayout?.viewport?.width &&
      pageLayout?.viewport?.height &&
      Array.isArray(pageLayout?.blocks) &&
      pageLayout.blocks.length > 0 &&
      Array.isArray(pageData?.translatedBlocks) &&
      pageData.translatedBlocks.length > 0,
  );
  const hasFigures = Array.isArray(pageData?.figureSnippets) && pageData.figureSnippets.length > 0;
  return hasStructuredText || hasFigures;
};

export const normalizeTranslationPage = (pageValue = {}) => {
  const pageLayout = normalizePageLayout(pageValue?.pageLayout);
  const translatedBlocks = normalizeTranslatedBlocks(pageValue?.translatedBlocks);
  const figureSnippets = normalizeFigureSnippets(pageValue?.figureSnippets);
  const normalizedPage = {
    sourceText: String(pageValue?.sourceText || ''),
    translatedText: String(pageValue?.translatedText || ''),
    translatedBlocks,
    figureSnippets,
    renderMode: pageValue?.renderMode === 'overlay' ? 'overlay' : 'plain',
    backgroundImage: typeof pageValue?.backgroundImage === 'string' ? pageValue.backgroundImage : '',
    pageLayout,
    excludedZones: normalizeExcludedZones(pageValue?.excludedZones),
    status: pageValue?.status || (pageValue?.translatedText ? 'success' : 'idle'),
    error: String(pageValue?.error || ''),
    updatedAt: pageValue?.updatedAt || null,
  };

  if (normalizedPage.renderMode === 'overlay' && !canRenderOverlay(normalizedPage)) {
    normalizedPage.renderMode = 'plain';
  }

  if (
    normalizedPage.renderMode === 'plain' &&
    canRenderOverlay(normalizedPage) &&
    (translatedBlocks.length > 0 || figureSnippets.length > 0)
  ) {
    normalizedPage.renderMode = 'overlay';
  }

  return normalizedPage;
};

export const normalizeTranslationState = (storedValue, pdfId = null) => {
  if (!storedValue) {
    return createEmptyTranslationState(pdfId);
  }

  const pages = Object.entries(storedValue.pages || {}).reduce((accumulator, [pageKey, pageValue]) => {
    const pageIndex = Number(pageKey);
    if (Number.isNaN(pageIndex)) {
      return accumulator;
    }

    accumulator[pageIndex] = normalizeTranslationPage(pageValue);
    return accumulator;
  }, {});

  return createEmptyTranslationState(pdfId ?? storedValue.pdfId ?? null, {
    currentPage: Math.max(0, Number(storedValue.currentPage) || 0),
    pages,
    updatedAt: storedValue.updatedAt || null,
  });
};
