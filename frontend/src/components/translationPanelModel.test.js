import assert from 'node:assert/strict';

import { createTranslationPanelViewModel } from './translationPanelModel.js';

const singleColumnLayout = {
  viewport: { width: 600, height: 800 },
  orientation: 'portrait',
  columnMode: 'single-column',
  blocks: [
    {
      id: 'block-1',
      text: 'Source paragraph',
      bbox: { left: 0.08, top: 0.16, width: 0.4, height: 0.08 },
      style: { fontSize: 12, fontWeight: 'normal', italic: false },
      readingOrder: 0,
    },
  ],
};

const run = () => {
  const plainTranslation = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'plain',
    translatedText: '这是图题的译文。',
    translatedBlocks: [],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainTranslation.canRenderFidelity, false);
  assert.equal(plainTranslation.canRenderStructuredFallback, false);
  assert.equal(plainTranslation.shouldShowPlainTranslation, true);

  const imageOnlyLegacyPage = createTranslationPanelViewModel({
    status: 'empty',
    renderMode: 'overlay',
    translatedText: '',
    translatedBlocks: [],
    figureSnippets: [
      {
        id: 'figure-1',
        type: 'figure',
        bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 },
        image: 'data:image/png;base64,figure',
      },
    ],
    pageLayout: singleColumnLayout,
  });
  assert.equal(imageOnlyLegacyPage.canRenderFidelity, false);
  assert.equal(imageOnlyLegacyPage.canRenderStructuredFallback, false);
  assert.equal(imageOnlyLegacyPage.shouldShowPlainTranslation, false);

  const structuredOverlay = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'overlay',
    translatedText: '这是正文译文。',
    translatedBlocks: [{ id: 'block-1', translatedText: '这是正文译文。' }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(structuredOverlay.canRenderFidelity, true);

  const plainWithExcludedZones = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'plain',
    translatedText: '这是图文混排页面的译文。',
    translatedBlocks: [],
    backgroundImage: 'data:image/png;base64,page',
    excludedZones: [{ type: 'figure', bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 } }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainWithExcludedZones.shouldShowPlainTranslation, true);

  console.log('frontend translation panel model tests passed');
};

run();
