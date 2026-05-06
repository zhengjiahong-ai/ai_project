import assert from 'node:assert/strict';

import {
  planPageTranslationState,
  preparePageTranslationRequest,
  shouldPreferPlainPageTranslation,
} from './pageTranslationRequest.js';

const samplePageLayout = {
  viewport: { width: 600, height: 800 },
  blocks: [
    {
      id: 'block-1',
      text: 'Figure 1. Overview of the pipeline.',
      bbox: { left: 0.52, top: 0.35, width: 0.28, height: 0.12 },
      style: { fontSize: 12, fontWeight: 'normal', italic: false },
    },
  ],
};

const run = () => {
  const plainFallbackRequest = preparePageTranslationRequest({
    pageText: 'Figure 1. Overview of the pipeline.',
    pageLayout: samplePageLayout,
    excludedZones: [
      {
        type: 'figure',
        bbox: { left: 0.5, top: 0.32, width: 0.34, height: 0.18 },
      },
    ],
  });
  assert.equal(plainFallbackRequest.shouldMarkEmpty, true);
  assert.equal(plainFallbackRequest.requestMode, 'plain');
  assert.equal(plainFallbackRequest.translationSourceText, '');
  assert.equal(plainFallbackRequest.requestPageLayout.blocks.length, 0);
  assert.equal(plainFallbackRequest.requestPayloadPageLayout, null);

  const figurePagePlainRequest = preparePageTranslationRequest({
    pageText: 'Body paragraph with a nearby figure.',
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [
        {
          id: 'block-1',
          text: 'Body paragraph with a nearby figure.',
          bbox: { left: 0.08, top: 0.18, width: 0.4, height: 0.08 },
          style: { fontSize: 12, fontWeight: 'normal', italic: false },
        },
      ],
    },
    excludedZones: [
      {
        type: 'figure',
        bbox: { left: 0.52, top: 0.32, width: 0.3, height: 0.2 },
      },
    ],
    preferPlain: true,
  });
  assert.equal(figurePagePlainRequest.requestMode, 'plain');
  assert.equal(figurePagePlainRequest.translationSourceText, 'Body paragraph with a nearby figure.');
  assert.equal(figurePagePlainRequest.requestPageLayout.blocks.length, 1);
  assert.equal(figurePagePlainRequest.requestPayloadPageLayout, null);

  const emptyRequest = preparePageTranslationRequest({
    pageText: '   ',
    pageLayout: samplePageLayout,
  });
  assert.equal(emptyRequest.shouldMarkEmpty, true);
  assert.equal(emptyRequest.requestMode, 'structured');
  assert.ok(emptyRequest.requestPayloadPageLayout);

  const structuredRequest = preparePageTranslationRequest({
    pageText: 'Body paragraph',
    pageLayout: {
      viewport: { width: 600, height: 800 },
      blocks: [
        {
          id: 'block-1',
          text: 'Body paragraph',
          bbox: { left: 0.08, top: 0.18, width: 0.4, height: 0.08 },
          style: { fontSize: 12, fontWeight: 'normal', italic: false },
        },
      ],
    },
    excludedZones: [],
  });
  assert.equal(structuredRequest.shouldMarkEmpty, false);
  assert.equal(structuredRequest.requestMode, 'structured');
  assert.equal(structuredRequest.translationSourceText, 'Body paragraph');
  assert.equal(structuredRequest.requestPayloadPageLayout.blocks.length, 1);

  assert.equal(
    shouldPreferPlainPageTranslation({
      excludedZones: [],
    }),
    false,
  );
  assert.equal(
    shouldPreferPlainPageTranslation({
      excludedZones: [{ type: 'figure', bbox: { left: 0.1, top: 0.1, width: 0.3, height: 0.3 } }],
    }),
    false,
  );
  assert.equal(
    shouldPreferPlainPageTranslation({
      excludedZones: [{ type: 'table', bbox: { left: 0.1, top: 0.1, width: 0.3, height: 0.3 } }],
    }),
    false,
  );
  assert.equal(
    shouldPreferPlainPageTranslation({
      excludedZones: [{ type: 'formula', bbox: { left: 0.1, top: 0.1, width: 0.3, height: 0.3 } }],
    }),
    false,
  );

  const requestPlan = planPageTranslationState({
    translationState: {
      pdfId: 'paper-1',
      currentPage: 0,
      pages: {},
    },
    pdfId: 'paper-1',
    pageIndex: 0,
    sourceText: 'Body paragraph',
    pageLayout: samplePageLayout,
    excludedZones: [],
    force: false,
    expectsStructuredResponse: false,
    shouldMarkEmpty: false,
    hasActiveRequest: false,
  });
  assert.equal(requestPlan.shouldRequest, true);
  assert.equal(requestPlan.nextState.currentPage, 0);
  assert.equal(requestPlan.nextState.pages[0].status, 'loading');
  assert.equal(requestPlan.nextState.pages[0].sourceText, 'Body paragraph');

  const loadingReusePlan = planPageTranslationState({
    translationState: requestPlan.nextState,
    pdfId: 'paper-1',
    pageIndex: 0,
    sourceText: 'Body paragraph',
    pageLayout: samplePageLayout,
    excludedZones: [],
    force: false,
    expectsStructuredResponse: false,
    shouldMarkEmpty: false,
    hasActiveRequest: true,
  });
  assert.equal(loadingReusePlan.shouldRequest, false);
  assert.equal(loadingReusePlan.nextState.pages[0].status, 'loading');

  console.log('frontend page translation request tests passed');
};

run();
