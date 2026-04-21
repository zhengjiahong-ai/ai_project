import { buildFidelityTranslationLayout, buildReadableTranslationLayout } from '../utils/pdfTranslationLayout.js';
import { canRenderOverlay } from '../utils/translationState.js';

const isRenderableExcludedZone = (zone) => {
  const bbox = zone?.bbox || {};
  return Boolean(zone?.type) && Number(bbox.width || 0) > 0 && Number(bbox.height || 0) > 0;
};

export const buildDisplayFigureSnippets = (pageData = null) => {
  const explicitFigures = Array.isArray(pageData?.figureSnippets) ? pageData.figureSnippets : [];
  if (explicitFigures.length > 0) {
    return explicitFigures;
  }

  const backgroundImage = typeof pageData?.backgroundImage === 'string' ? pageData.backgroundImage : '';
  const excludedZones = Array.isArray(pageData?.excludedZones) ? pageData.excludedZones : [];
  const viewport = pageData?.pageLayout?.viewport || null;
  if (!backgroundImage || excludedZones.length === 0 || !viewport) {
    return [];
  }

  return excludedZones
    .filter(isRenderableExcludedZone)
    .map((zone, index) => ({
      id: `excluded-zone-${index + 1}`,
      type: String(zone.type || 'figure'),
      bbox: zone.bbox,
      image: backgroundImage,
      viewport,
      cropMode: 'viewport',
    }));
};

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
  const rawFigureSnippets = Array.isArray(pageData?.figureSnippets) ? pageData.figureSnippets : [];
  const displayFigureSnippets = buildDisplayFigureSnippets(pageData);
  const overlayEnabled = pageData?.renderMode === 'overlay' || canRenderOverlay(pageData);
  const baseFidelityLayout = buildFidelityTranslationLayout(pageData?.pageLayout, translatedBlocks, rawFigureSnippets);
  const readableLayout = buildReadableTranslationLayout(pageData?.pageLayout, translatedBlocks, rawFigureSnippets);
  const hasTranslatedBlocks = translatedBlocks.length > 0;
  const hasFigures = displayFigureSnippets.length > 0;
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
    displayFigureSnippets,
    shouldRenderFigureGallery: hasFigures && !hasTranslatedBlocks,
    shouldShowPlainTranslation:
      Boolean(translatedText) &&
      !canRenderFidelity &&
      !canRenderStructuredFallback &&
      !canRenderPlainColumnFallback,
  };
};
