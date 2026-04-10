import assert from 'node:assert/strict';

import {
  buildPageLayout,
  buildReadableTranslationLayout,
  buildTranslationRequestPageLayout,
  doesBboxIntersect,
  isBlockInExcludedZone,
  normalizeFigureSnippets,
} from './pdfTranslationLayout.js';

const run = () => {
  const viewport = { width: 600, height: 800 };
  const textContent = {
    items: [
      {
        str: 'Semantic Alignment-Enhanced Code Translation',
        transform: [18, 0, 0, 18, 70, 740],
        width: 360,
        height: 18,
        fontName: 'Times-Bold',
      },
      {
        str: 'This is the first paragraph.',
        transform: [12, 0, 0, 12, 60, 640],
        width: 170,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'This is the second line.',
        transform: [12, 0, 0, 12, 60, 625],
        width: 155,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Figure 1. Overview',
        transform: [11, 0, 0, 11, 340, 500],
        width: 110,
        height: 11,
        fontName: 'Times-Italic',
      },
    ],
  };

  const { pageText, pageLayout } = buildPageLayout(textContent, viewport);
  assert.match(pageText, /Semantic Alignment-Enhanced Code Translation/);
  assert.equal(pageLayout.viewport.width, 600);
  assert.ok(pageLayout.blocks.length >= 3);
  assert.equal(pageLayout.blocks[0].style.fontWeight, 'bold');

  const figureSnippets = normalizeFigureSnippets([
    {
      id: 'figure-1',
      type: 'figure',
      bbox: { left: 0.54, top: 0.34, width: 0.28, height: 0.16 },
      image: 'data:image/png;base64,figure',
    },
  ]);
  assert.equal(figureSnippets.length, 1);

  const readableLayout = buildReadableTranslationLayout(
    pageLayout,
    [
      { id: pageLayout.blocks[0].id, translatedText: '语义对齐增强的代码翻译' },
      { id: pageLayout.blocks[1].id, translatedText: '这是第一段。' },
      { id: pageLayout.blocks[2].id, translatedText: '这是第二段。' },
    ],
    figureSnippets,
  );
  assert.equal(readableLayout.sections.length >= 1, true);
  assert.equal(readableLayout.sections[0].items[0].role, 'title');
  assert.equal(readableLayout.summary.totalFigures, 1);
  assert.equal(
    readableLayout.sections.some((section) =>
      section.type === 'columns'
        ? [...section.left, ...section.right].some((item) => item.kind === 'figure')
        : section.items.some((item) => item.kind === 'figure'),
    ),
    true,
  );

  const excludedZones = [
    {
      type: 'figure',
      bbox: {
        left: 0.52,
        top: 0.35,
        width: 0.3,
        height: 0.12,
      },
    },
  ];
  const requestLayout = buildTranslationRequestPageLayout(pageLayout, excludedZones, 2);
  assert.equal(requestLayout.excludedZonesVersion, 2);
  assert.ok(requestLayout.blocks.length < pageLayout.blocks.length);
  assert.ok(requestLayout.blocks.every((block) => !isBlockInExcludedZone(block, excludedZones)));

  assert.equal(
    doesBboxIntersect(
      { left: 0.1, top: 0.1, width: 0.2, height: 0.2 },
      { left: 0.25, top: 0.2, width: 0.2, height: 0.2 },
    ),
    true,
  );
  assert.equal(
    doesBboxIntersect(
      { left: 0.1, top: 0.1, width: 0.05, height: 0.05 },
      { left: 0.3, top: 0.3, width: 0.1, height: 0.1 },
    ),
    false,
  );

  console.log('frontend pdf translation layout tests passed');
};

run();
