import { buildFidelityTranslationLayout, buildReadableTranslationLayout } from '../utils/pdfTranslationLayout.js';
import { canRenderOverlay } from '../utils/translationState.js';
import { buildPanoramicTranslation, usesUnpositionedTranslation, hasMath } from '../utils/panoramicTranslation.js';

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

export const createTranslationPanelViewModel = (pageData = null) => {
  const translatedText = String(pageData?.translatedText || '');
  const translatedBlocks = Array.isArray(pageData?.translatedBlocks) ? pageData.translatedBlocks : [];
  const overlayEnabled = pageData?.renderMode === 'overlay' || canRenderOverlay(pageData);
  const baseFidelityLayout = buildFidelityTranslationLayout(pageData?.pageLayout, translatedBlocks);
  const readableLayout = buildReadableTranslationLayout(pageData?.pageLayout, translatedBlocks);
  const hasTranslatedBlocks = translatedBlocks.length > 0;
  const panoramicLayout = buildPanoramicTranslation(pageData?.pageLayout, translatedBlocks, pageData?.excludedZones || []);
  const panoramicText = panoramicLayout?.sections.flatMap(section => section.type === 'columns'
    ? [...section.left, ...section.right] : section.items).filter(item => item.kind === 'translation')
    .map(item => item.translatedText).join('\n\n');
  const hasOriginalMath = (pageData?.pageLayout?.blocks || []).some(block => hasMath(block.text)) || /⟦原式\d+⟧/.test(translatedText);
  const mathNotice = hasOriginalMath && translatedText
    ? pageData?.mathProtectionVersion >= 1
      ? '原式标记对应原图中的数学表达式，请结合原图阅读。'
      : '旧译文未保护行内公式，请以原图为准。'
    : '';
  const visibleArtifactText = usesUnpositionedTranslation(pageData?.pageLayout, translatedBlocks) ? translatedText : panoramicText;
  const canRenderFidelity = hasTranslatedBlocks && Boolean(baseFidelityLayout?.positionedItems?.length) && overlayEnabled;
  const canRenderStructuredFallback =
    hasTranslatedBlocks && !canRenderFidelity && Boolean(readableLayout?.sections?.length) && overlayEnabled;
  const canRenderPlainColumnFallback =
    Boolean(translatedText) &&
    !canRenderFidelity &&
    !canRenderStructuredFallback &&
    getPlainFallbackColumnMode(pageData?.pageLayout) === 'two-column';

  return {
    panoramicArtifactText: visibleArtifactText && mathNotice ? `> ${mathNotice}\n\n${visibleArtifactText}` : visibleArtifactText,
    mathNotice,
    panoramicLayout,
    panoramicText,
    baseFidelityLayout,
    readableLayout,
    canRenderFidelity,
    canRenderStructuredFallback,
    canRenderPlainColumnFallback,
    shouldShowPlainTranslation:
      Boolean(translatedText) &&
      !canRenderFidelity &&
      !canRenderStructuredFallback &&
      !canRenderPlainColumnFallback,
  };
};
