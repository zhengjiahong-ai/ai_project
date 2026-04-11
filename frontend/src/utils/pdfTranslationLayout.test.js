import assert from 'node:assert/strict';

import {
  buildFidelityTranslationLayout,
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

  const twoColumnTextContent = {
    items: [
      {
        str: 'A Cross-Column Paper Title',
        transform: [18, 0, 0, 18, 90, 740],
        width: 420,
        height: 18,
        fontName: 'Times-Bold',
      },
      {
        str: 'Left line 1',
        transform: [12, 0, 0, 12, 60, 640],
        width: 120,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right line 1',
        transform: [12, 0, 0, 12, 340, 640],
        width: 120,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left line 2',
        transform: [12, 0, 0, 12, 60, 625],
        width: 120,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right line 2',
        transform: [12, 0, 0, 12, 340, 625],
        width: 120,
        height: 12,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageText: twoColumnPageText, pageLayout: twoColumnPageLayout } = buildPageLayout(twoColumnTextContent, viewport);
  assert.equal(twoColumnPageLayout.blocks.length, 5);
  assert.match(twoColumnPageLayout.blocks[0].text, /A Cross-Column Paper Title/);
  assert.match(twoColumnPageLayout.blocks[1].text, /Left line 1/);
  assert.match(twoColumnPageLayout.blocks[2].text, /Left line 2/);
  assert.match(twoColumnPageLayout.blocks[3].text, /Right line 1/);
  assert.match(twoColumnPageLayout.blocks[4].text, /Right line 2/);
  assert.ok(twoColumnPageText.indexOf('A Cross-Column Paper Title') < twoColumnPageText.indexOf('Left line 1'));
  assert.ok(twoColumnPageText.indexOf('Left line 1') < twoColumnPageText.indexOf('Right line 1'));
  assert.ok(twoColumnPageText.indexOf('Left line 2') < twoColumnPageText.indexOf('Right line 1'));
  assert.ok(twoColumnPageLayout.blocks[2].readingOrder < twoColumnPageLayout.blocks[3].readingOrder);

  const twoColumnFidelityLayout = buildFidelityTranslationLayout(
    twoColumnPageLayout,
    twoColumnPageLayout.blocks.map((block) => ({ id: block.id, translatedText: `Translated ${block.text}` })),
  );
  assert.equal(twoColumnFidelityLayout.orientation, 'portrait');
  assert.equal(twoColumnFidelityLayout.columnMode, 'two-column');
  const leftLineItem = twoColumnFidelityLayout.positionedItems.find((item) => item.id === twoColumnPageLayout.blocks[1].id);
  const rightLineItem = twoColumnFidelityLayout.positionedItems.find((item) => item.id === twoColumnPageLayout.blocks[3].id);
  assert.ok(leftLineItem.left < 0.5);
  assert.ok(rightLineItem.left > 0.5);

  const slightlyWideColumnLayout = {
    viewport,
    blocks: [
      {
        id: 'title',
        text: 'Wide title',
        bbox: { left: 0.14, top: 0.08, width: 0.72, height: 0.05 },
        style: { fontSize: 20, fontWeight: 'bold', italic: false, textAlign: 'left' },
        readingOrder: 0,
      },
      {
        id: 'left-wide',
        text: 'Left column that slightly reaches the gutter',
        bbox: { left: 0.18, top: 0.28, width: 0.38, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 1,
      },
      {
        id: 'right-wide',
        text: 'Right column block',
        bbox: { left: 0.54, top: 0.28, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 2,
      },
    ],
  };
  const slightlyWideFidelityLayout = buildFidelityTranslationLayout(
    slightlyWideColumnLayout,
    slightlyWideColumnLayout.blocks.map((block) => ({ id: block.id, translatedText: `Translated ${block.id}` })),
  );
  const slightlyWideLeftBlock = slightlyWideFidelityLayout.positionedItems.find((item) => item.id === 'left-wide');
  assert.equal(slightlyWideFidelityLayout.columnMode, 'two-column');
  assert.equal(slightlyWideLeftBlock.lane, 'left');
  assert.ok(slightlyWideLeftBlock.width <= 0.3);

  const tightGutterTextContent = {
    items: [
      {
        str: 'Left wide line',
        transform: [12, 0, 0, 12, 60, 640],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right close line',
        transform: [12, 0, 0, 12, 340, 640],
        width: 190,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left wide line 2',
        transform: [12, 0, 0, 12, 60, 625],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right close line 2',
        transform: [12, 0, 0, 12, 340, 625],
        width: 190,
        height: 12,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageText: tightGutterPageText, pageLayout: tightGutterPageLayout } = buildPageLayout(tightGutterTextContent, viewport);
  assert.equal(tightGutterPageLayout.blocks.length, 4);
  assert.match(tightGutterPageLayout.blocks[0].text, /Left wide line/);
  assert.match(tightGutterPageLayout.blocks[1].text, /Left wide line 2/);
  assert.match(tightGutterPageLayout.blocks[2].text, /Right close line/);
  assert.match(tightGutterPageLayout.blocks[3].text, /Right close line 2/);
  assert.ok(tightGutterPageText.indexOf('Left wide line 2') < tightGutterPageText.indexOf('Right close line'));

  const landscapeViewport = { width: 800, height: 500 };
  const landscapeTextContent = {
    items: [
      {
        str: 'Landscape left block',
        transform: [14, 0, 0, 14, 70, 410],
        width: 180,
        height: 14,
        fontName: 'Times-Roman',
      },
      {
        str: 'Landscape right block',
        transform: [14, 0, 0, 14, 520, 410],
        width: 190,
        height: 14,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageLayout: landscapePageLayout } = buildPageLayout(landscapeTextContent, landscapeViewport);
  const landscapeFidelityLayout = buildFidelityTranslationLayout(
    landscapePageLayout,
    landscapePageLayout.blocks.map((block) => ({ id: block.id, translatedText: `Translated ${block.text}` })),
  );
  assert.equal(landscapeFidelityLayout.orientation, 'landscape');
  assert.equal(landscapeFidelityLayout.pageAspectRatio, 0.625);
  assert.ok(landscapeFidelityLayout.positionedItems[0].left < landscapeFidelityLayout.positionedItems[1].left);

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

  const fidelityLayout = buildFidelityTranslationLayout(
    pageLayout,
    [
      { id: pageLayout.blocks[0].id, translatedText: '语义对齐增强的代码翻译' },
      { id: pageLayout.blocks[1].id, translatedText: '这是第一段。' },
      { id: pageLayout.blocks[2].id, translatedText: '这是第二段。' },
    ],
    figureSnippets,
  );
  assert.ok(fidelityLayout);
  assert.equal(fidelityLayout.positionedItems[0].left, pageLayout.blocks[0].bbox.left);
  assert.equal(
    fidelityLayout.positionedItems[0].top,
    Number((pageLayout.blocks[0].bbox.top * (viewport.height / viewport.width)).toFixed(6)),
  );
  assert.equal(fidelityLayout.positionedItems[0].style.textAlign, 'center');
  assert.equal(
    fidelityLayout.positionedItems.some((item) => item.kind === 'figure' && item.left === figureSnippets[0].bbox.left),
    true,
  );

  const twoColumnLayout = {
    viewport,
    blocks: [
      {
        id: 'block-1',
        text: 'A centered title',
        bbox: { left: 0.14, top: 0.08, width: 0.72, height: 0.05 },
        style: { fontSize: 20, fontWeight: 'bold', italic: false, textAlign: 'left' },
        readingOrder: 0,
      },
      {
        id: 'block-2',
        text: 'Left column first block',
        bbox: { left: 0.08, top: 0.24, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 1,
      },
      {
        id: 'block-3',
        text: 'Right column first block',
        bbox: { left: 0.56, top: 0.24, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 2,
      },
      {
        id: 'block-4',
        text: 'Left column second block',
        bbox: { left: 0.08, top: 0.36, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 3,
      },
      {
        id: 'block-5',
        text: 'Right column second block',
        bbox: { left: 0.56, top: 0.36, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 4,
      },
      {
        id: 'block-6',
        text: 'A cross-column conclusion line',
        bbox: { left: 0.12, top: 0.5, width: 0.76, height: 0.05 },
        style: { fontSize: 13, fontWeight: 'bold', italic: false, textAlign: 'left' },
        readingOrder: 5,
      },
      {
        id: 'block-7',
        text: 'A left-column footer block',
        bbox: { left: 0.08, top: 0.95, width: 0.36, height: 0.04 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 6,
      },
    ],
  };

  const twoColumnTranslations = twoColumnLayout.blocks.map((block) => ({
    id: block.id,
    translatedText: `Translated ${block.id}`,
  }));
  const overflowLayout = buildFidelityTranslationLayout(twoColumnLayout, twoColumnTranslations, [], {
    'block-2': 0.48,
  });
  assert.ok(overflowLayout);

  const leftOverflowBlock = overflowLayout.positionedItems.find((item) => item.id === 'block-2');
  const leftFollowingBlock = overflowLayout.positionedItems.find((item) => item.id === 'block-4');
  const rightFollowingBlock = overflowLayout.positionedItems.find((item) => item.id === 'block-5');
  const crossColumnBlock = overflowLayout.positionedItems.find((item) => item.id === 'block-6');
  const originalLeftSecondTop = Number((twoColumnLayout.blocks[3].bbox.top * (viewport.height / viewport.width)).toFixed(6));
  const originalRightSecondTop = Number((twoColumnLayout.blocks[4].bbox.top * (viewport.height / viewport.width)).toFixed(6));
  const originalCrossTop = Number((twoColumnLayout.blocks[5].bbox.top * (viewport.height / viewport.width)).toFixed(6));

  assert.ok(leftOverflowBlock.height > leftOverflowBlock.baseHeight);
  assert.ok(leftFollowingBlock.top > originalLeftSecondTop);
  assert.equal(rightFollowingBlock.top, originalRightSecondTop);
  assert.ok(crossColumnBlock.top > originalCrossTop);

  const pageGrowthLayout = {
    viewport,
    blocks: [
      {
        id: 'growth-1',
        text: 'A very long block',
        bbox: { left: 0.08, top: 0.12, width: 0.36, height: 0.08 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 0,
      },
      {
        id: 'growth-2',
        text: 'A lower block',
        bbox: { left: 0.08, top: 0.84, width: 0.36, height: 0.05 },
        style: { fontSize: 12, fontWeight: 'normal', italic: false, textAlign: 'left' },
        readingOrder: 1,
      },
    ],
  };
  const pageGrowthTranslations = pageGrowthLayout.blocks.map((block) => ({
    id: block.id,
    translatedText: `Translated ${block.id}`,
  }));
  const baselineGrowthLayout = buildFidelityTranslationLayout(pageGrowthLayout, pageGrowthTranslations, []);
  const expandedGrowthLayout = buildFidelityTranslationLayout(pageGrowthLayout, pageGrowthTranslations, [], {
    'growth-1': 1.2,
  });
  assert.ok(expandedGrowthLayout.pageHeight > baselineGrowthLayout.pageHeight);

  const figureOnlyLayout = buildFidelityTranslationLayout(
    {
      viewport,
      blocks: [],
    },
    [],
    figureSnippets,
  );
  assert.ok(figureOnlyLayout);
  assert.equal(figureOnlyLayout.positionedItems.length, 1);
  assert.equal(figureOnlyLayout.positionedItems[0].kind, 'figure');

  assert.equal(buildFidelityTranslationLayout({ blocks: [] }, twoColumnTranslations, figureSnippets), null);

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
