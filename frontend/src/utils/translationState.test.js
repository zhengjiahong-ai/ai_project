import assert from 'node:assert/strict';

import {
  canRenderOverlay,
  createEmptyTranslationState,
  normalizeTranslationPage,
  normalizeTranslationState,
} from './translationState.js';

const run = () => {
  const emptyState = createEmptyTranslationState('paper-1');
  assert.equal(emptyState.pdfId, 'paper-1');
  assert.deepEqual(emptyState.pages, {});

  const legacyState = normalizeTranslationState(
    {
      pdfId: 'paper-1',
      currentPage: 2,
      pages: {
        2: {
          sourceText: 'source',
          translatedText: 'translated',
          status: 'success',
        },
      },
    },
    'paper-1',
  );
  assert.equal(legacyState.currentPage, 2);
  assert.equal(legacyState.pages[2].renderMode, 'plain');
  assert.equal(legacyState.pages[2].translatedText, 'translated');

  const restoredLoadingState = normalizeTranslationState(
    {
      pdfId: 'paper-1',
      currentPage: 1,
      pages: {
        1: {
          sourceText: 'source',
          status: 'loading',
          updatedAt: Date.now(),
        },
      },
    },
    'paper-1',
  );
  assert.equal(restoredLoadingState.pages[1].status, 'idle');

  const overlayPage = normalizeTranslationPage({
    sourceText: 'source',
    translatedText: 'translated',
    renderMode: 'overlay',
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [
        {
          id: 'block-1',
          text: 'source',
          bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 },
          style: { fontSize: 12, fontWeight: 'normal', italic: false },
        },
      ],
    },
    translatedBlocks: [{ id: 'block-1', translatedText: 'translated' }],
    figureSnippets: [
      {
        id: 'figure-1',
        type: 'figure',
        bbox: { left: 0.52, top: 0.5, width: 0.2, height: 0.2 },
        image: 'data:image/png;base64,figure',
      },
    ],
    excludedZones: [{ type: 'figure', bbox: { left: 0.5, top: 0.5, width: 0.2, height: 0.2 } }],
  });
  assert.equal(overlayPage.renderMode, 'overlay');
  assert.equal(canRenderOverlay(overlayPage), true);
  assert.equal(Object.hasOwn(overlayPage, 'figureSnippets'), false);
  assert.equal(Object.hasOwn(overlayPage, 'backgroundImage'), false);
  assert.equal(overlayPage.pageLayout.orientation, 'portrait');
  assert.equal(overlayPage.pageLayout.columnMode, 'single-column');

  const preservedLayoutMetaPage = normalizeTranslationPage({
    pageLayout: {
      viewport: { width: 600, height: 800 },
      orientation: 'portrait',
      columnMode: 'two-column',
      blocks: [
        {
          id: 'block-1',
          text: 'source',
          bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 },
        },
      ],
    },
  });
  assert.equal(preservedLayoutMetaPage.pageLayout.orientation, 'portrait');
  assert.equal(preservedLayoutMetaPage.pageLayout.columnMode, 'two-column');

  const figureOnlyPage = normalizeTranslationPage({
    renderMode: 'plain',
    backgroundImage: 'data:image/png;base64,page',
    figureSnippets: [
      {
        id: 'figure-1',
        type: 'table',
        bbox: { left: 0.2, top: 0.3, width: 0.45, height: 0.3 },
        image: 'data:image/png;base64,table',
      },
    ],
  });
  assert.equal(figureOnlyPage.renderMode, 'plain');
  assert.equal(canRenderOverlay(figureOnlyPage), false);
  assert.equal(Object.hasOwn(figureOnlyPage, 'figureSnippets'), false);
  assert.equal(Object.hasOwn(figureOnlyPage, 'backgroundImage'), false);

  const downgradedPage = normalizeTranslationPage({
    renderMode: 'overlay',
    translatedBlocks: [{ id: 'block-1', translatedText: 'translated' }],
  });
  assert.equal(downgradedPage.renderMode, 'plain');
  assert.equal(canRenderOverlay(downgradedPage), false);

  const structuredLegacyPage = normalizeTranslationPage({
    sourceText: 'source',
    translatedText: 'plain translated text',
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [
        {
          id: 'block-1',
          text: 'source',
          bbox: { left: 0.1, top: 0.1, width: 0.2, height: 0.1 },
          style: { fontSize: 12, fontWeight: 'normal', italic: false },
        },
      ],
    },
    translatedBlocks: [{ id: 'block-1', translatedText: 'structured translation' }],
  });
  assert.equal(structuredLegacyPage.renderMode, 'overlay');

  console.log('frontend translation state tests passed');
};

run();
