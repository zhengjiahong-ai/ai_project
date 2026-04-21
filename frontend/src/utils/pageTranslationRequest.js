import { buildTranslationRequestPageLayout } from './pdfTranslationLayout.js';

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
