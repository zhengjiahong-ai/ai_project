import { buildTranslationRequestPageLayout } from './pdfTranslationLayout.js';

export const preparePageTranslationRequest = ({
  pageText = '',
  pageLayout = null,
  excludedZones = [],
}) => {
  const sourceText = String(pageText || '').trim();
  const requestPageLayout = pageLayout
    ? buildTranslationRequestPageLayout(pageLayout, excludedZones, pageLayout?.excludedZonesVersion || 1)
    : null;
  const hasStructuredBlocks = Boolean(requestPageLayout?.blocks?.length);
  const translationSourceText = hasStructuredBlocks
    ? requestPageLayout.blocks.map((block) => block.text).join('\n\n').trim()
    : sourceText;

  return {
    sourceText,
    requestPageLayout,
    requestPayloadPageLayout: hasStructuredBlocks ? requestPageLayout : null,
    hasStructuredBlocks,
    requestMode: hasStructuredBlocks ? 'structured' : 'plain',
    translationSourceText,
    shouldMarkEmpty: !sourceText,
  };
};
