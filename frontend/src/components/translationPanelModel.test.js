import assert from 'node:assert/strict';

import { buildDisplayFigureSnippets, createTranslationPanelViewModel } from './translationPanelModel.js';

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

const figureSnippet = {
  id: 'figure-1',
  type: 'figure',
  bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 },
  image: 'data:image/png;base64,figure',
};

const run = () => {
  const plainWithFigures = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'overlay',
    translatedText: '这是图题的译文。',
    translatedBlocks: [],
    figureSnippets: [figureSnippet],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainWithFigures.canRenderFidelity, false);
  assert.equal(plainWithFigures.canRenderStructuredFallback, false);
  assert.equal(plainWithFigures.shouldRenderFigureGallery, true);
  assert.equal(plainWithFigures.shouldShowPlainTranslation, true);

  const figureOnlyEmpty = createTranslationPanelViewModel({
    status: 'empty',
    renderMode: 'overlay',
    translatedText: '',
    translatedBlocks: [],
    figureSnippets: [figureSnippet],
    pageLayout: singleColumnLayout,
  });
  assert.equal(figureOnlyEmpty.canRenderFidelity, false);
  assert.equal(figureOnlyEmpty.canRenderStructuredFallback, false);
  assert.equal(figureOnlyEmpty.shouldRenderFigureGallery, true);
  assert.equal(figureOnlyEmpty.shouldShowPlainTranslation, false);

  const structuredOverlay = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'overlay',
    translatedText: '这是正文译文。',
    translatedBlocks: [{ id: 'block-1', translatedText: '这是正文译文。' }],
    figureSnippets: [figureSnippet],
    pageLayout: singleColumnLayout,
  });
  assert.equal(structuredOverlay.canRenderFidelity, true);
  assert.equal(structuredOverlay.shouldRenderFigureGallery, false);

  const derivedDisplayFigures = buildDisplayFigureSnippets({
    status: 'success',
    translatedText: '这是正文译文。',
    translatedBlocks: [],
    figureSnippets: [],
    backgroundImage: 'data:image/png;base64,page',
    excludedZones: [{ type: 'figure', bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 } }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(derivedDisplayFigures.length, 1);
  assert.equal(derivedDisplayFigures[0].cropMode, 'viewport');

  const plainWithDerivedFigures = createTranslationPanelViewModel({
    status: 'success',
    renderMode: 'plain',
    translatedText: '这是图文混排页面的译文。',
    translatedBlocks: [],
    figureSnippets: [],
    backgroundImage: 'data:image/png;base64,page',
    excludedZones: [{ type: 'figure', bbox: { left: 0.5, top: 0.34, width: 0.3, height: 0.22 } }],
    pageLayout: singleColumnLayout,
  });
  assert.equal(plainWithDerivedFigures.displayFigureSnippets.length, 1);
  assert.equal(plainWithDerivedFigures.shouldRenderFigureGallery, true);

  console.log('frontend translation panel model tests passed');
};

run();
