import { buildFidelityTranslationLayout, buildReadableTranslationLayout } from '../utils/pdfTranslationLayout.js';
import { canRenderOverlay } from '../utils/translationState.js';

export const getPlainFallbackColumnMode = (pageLayout) => {
  const viewport = pageLayout?.viewport || {};
  const blocks = Array.isArray(pageLayout?.blocks) ? pageLayout.blocks : [];
  const declaredOrientation = pageLayout?.orientation;
  const declaredColumnMode = pageLayout?.columnMode;
  const isPortrait =
    declaredOrientation === 'portrait' || Number(viewport?.height || 0) >= Number(viewport?.width || 0);

  if (declaredOrientation === 'landscape') {
    return 'single-column';
  }

  if (isPortrait && declaredColumnMode === 'two-column') {
    return 'two-column';
  }

  if (!isPortrait || blocks.length < 2) {
    return 'single-column';
  }

  const bodyBlocks = blocks.filter((block) => {
    const bbox = block?.bbox || {};
    const center = Number(bbox.left || 0) + Number(bbox.width || 0) / 2;
    return Number(bbox.top || 0) >= 0.14 && Number(bbox.width || 0) <= 0.58 && center >= 0.06 && center <= 0.94;
  });
  const hasLeftColumn = bodyBlocks.some((block) => (block.bbox.left || 0) + (block.bbox.width || 0) / 2 < 0.5);
  const hasRightColumn = bodyBlocks.some((block) => (block.bbox.left || 0) + (block.bbox.width || 0) / 2 >= 0.5);
  return hasLeftColumn && hasRightColumn ? 'two-column' : 'single-column';
};

export const sortFigureSnippetsForDisplay = (figureSnippets = []) =>
  [...(Array.isArray(figureSnippets) ? figureSnippets : [])].sort((left, right) => {
    const topDelta = Number(left?.bbox?.top || 0) - Number(right?.bbox?.top || 0);
    if (Math.abs(topDelta) > 0.01) {
      return topDelta;
    }

    return Number(left?.bbox?.left || 0) - Number(right?.bbox?.left || 0);
  });

export const createTranslationPanelViewModel = (pageData = null) => {
  const translatedText = String(pageData?.translatedText || '');
  const translatedBlocks = Array.isArray(pageData?.translatedBlocks) ? pageData.translatedBlocks : [];
  const figureSnippets = Array.isArray(pageData?.figureSnippets) ? pageData.figureSnippets : [];
  const overlayEnabled = pageData?.renderMode === 'overlay' || canRenderOverlay(pageData);
  const baseFidelityLayout = buildFidelityTranslationLayout(pageData?.pageLayout, translatedBlocks, figureSnippets);
  const readableLayout = buildReadableTranslationLayout(pageData?.pageLayout, translatedBlocks, figureSnippets);
  const hasTranslatedBlocks = translatedBlocks.length > 0;
  const hasFigures = figureSnippets.length > 0;
  const canRenderFidelity = hasTranslatedBlocks && Boolean(baseFidelityLayout?.positionedItems?.length) && overlayEnabled;
  const canRenderStructuredFallback =
    hasTranslatedBlocks && !canRenderFidelity && Boolean(readableLayout?.sections?.length) && overlayEnabled;
  const canRenderPlainColumnFallback =
    Boolean(translatedText) &&
    !canRenderFidelity &&
    !canRenderStructuredFallback &&
    getPlainFallbackColumnMode(pageData?.pageLayout) === 'two-column';

  return {
    baseFidelityLayout,
    readableLayout,
    canRenderFidelity,
    canRenderStructuredFallback,
    canRenderPlainColumnFallback,
    shouldRenderFigureGallery: hasFigures && !hasTranslatedBlocks,
    shouldShowPlainTranslation:
      Boolean(translatedText) &&
      !canRenderFidelity &&
      !canRenderStructuredFallback &&
      !canRenderPlainColumnFallback,
  };
};
