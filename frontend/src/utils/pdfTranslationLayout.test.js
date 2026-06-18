import assert from 'node:assert/strict';

import {
  buildFidelityTranslationLayout,
  buildPageLayout,
  buildReadableTranslationLayout,
  buildTranslationRequestPageLayout,
  doesBboxIntersect,
  isBlockInExcludedZone,
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
  assert.equal(twoColumnPageLayout.blocks.length, 3);
  assert.match(twoColumnPageLayout.blocks[0].text, /A Cross-Column Paper Title/);
  assert.match(twoColumnPageLayout.blocks[1].text, /Left line 1/);
  assert.match(twoColumnPageLayout.blocks[1].text, /Left line 2/);
  assert.match(twoColumnPageLayout.blocks[2].text, /Right line 1/);
  assert.match(twoColumnPageLayout.blocks[2].text, /Right line 2/);
  assert.ok(twoColumnPageText.indexOf('A Cross-Column Paper Title') < twoColumnPageText.indexOf('Left line 1'));
  assert.ok(twoColumnPageText.indexOf('Left line 1') < twoColumnPageText.indexOf('Right line 1'));
  assert.ok(twoColumnPageText.indexOf('Left line 2') < twoColumnPageText.indexOf('Right line 1'));
  assert.ok(twoColumnPageLayout.blocks[1].readingOrder < twoColumnPageLayout.blocks[2].readingOrder);

  const unevenColumnStartTextContent = {
    items: [
      {
        str: 'B. Radar Model',
        transform: [12, 0, 0, 12, 340, 708],
        width: 150,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right column body 1',
        transform: [12, 0, 0, 12, 340, 650],
        width: 180,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right column body 2',
        transform: [12, 0, 0, 12, 340, 635],
        width: 180,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right column body 3',
        transform: [12, 0, 0, 12, 340, 620],
        width: 180,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left continuation 1',
        transform: [12, 0, 0, 12, 60, 560],
        width: 210,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left continuation 2',
        transform: [12, 0, 0, 12, 60, 545],
        width: 210,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left continuation 3',
        transform: [12, 0, 0, 12, 60, 530],
        width: 210,
        height: 12,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageText: unevenColumnStartPageText, pageLayout: unevenColumnStartPageLayout } = buildPageLayout(
    unevenColumnStartTextContent,
    viewport,
  );
  assert.equal(unevenColumnStartPageLayout.columnMode, 'two-column');
  assert.ok(unevenColumnStartPageText.indexOf('Left continuation 1') < unevenColumnStartPageText.indexOf('B. Radar Model'));

  const twoColumnFidelityLayout = buildFidelityTranslationLayout(
    twoColumnPageLayout,
    twoColumnPageLayout.blocks.map((block) => ({ id: block.id, translatedText: `Translated ${block.text}` })),
  );
  assert.equal(twoColumnFidelityLayout.orientation, 'portrait');
  assert.equal(twoColumnFidelityLayout.columnMode, 'two-column');
  const leftLineItem = twoColumnFidelityLayout.positionedItems.find((item) => item.id === twoColumnPageLayout.blocks[1].id);
  const rightLineItem = twoColumnFidelityLayout.positionedItems.find((item) => item.id === twoColumnPageLayout.blocks[2].id);
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
  assert.equal(tightGutterPageLayout.blocks.length, 2);
  assert.match(tightGutterPageLayout.blocks[0].text, /Left wide line/);
  assert.match(tightGutterPageLayout.blocks[0].text, /Left wide line 2/);
  assert.match(tightGutterPageLayout.blocks[1].text, /Right close line/);
  assert.match(tightGutterPageLayout.blocks[1].text, /Right close line 2/);
  assert.ok(tightGutterPageText.indexOf('Left wide line 2') < tightGutterPageText.indexOf('Right close line'));

  const rawColumnOrderTextContent = {
    items: [
      {
        str: 'A Cross-Column Header',
        transform: [18, 0, 0, 18, 80, 740],
        width: 440,
        height: 18,
        fontName: 'Times-Bold',
      },
      {
        str: 'Left column first line',
        transform: [12, 0, 0, 12, 60, 640],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Left column second line',
        transform: [12, 0, 0, 12, 60, 625],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'arXiv:2409.19894v4 [cs.SE] 17 Sep 2025',
        transform: [0, 20, -20, 0, 32, 223],
        width: 344,
        height: 20,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right column first line',
        transform: [12, 0, 0, 12, 312, 640],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
      {
        str: 'Right column second line',
        transform: [12, 0, 0, 12, 312, 625],
        width: 240,
        height: 12,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageText: rawColumnOrderPageText, pageLayout: rawColumnOrderPageLayout } = buildPageLayout(
    rawColumnOrderTextContent,
    viewport,
  );
  assert.equal(rawColumnOrderPageLayout.orientation, 'portrait');
  assert.equal(rawColumnOrderPageLayout.columnMode, 'two-column');
  assert.equal(rawColumnOrderPageLayout.blocks.length, 3);
  assert.match(rawColumnOrderPageLayout.blocks[0].text, /A Cross-Column Header/);
  assert.match(rawColumnOrderPageLayout.blocks[1].text, /Left column first line/);
  assert.match(rawColumnOrderPageLayout.blocks[1].text, /Left column second line/);
  assert.match(rawColumnOrderPageLayout.blocks[2].text, /Right column first line/);
  assert.match(rawColumnOrderPageLayout.blocks[2].text, /Right column second line/);
  assert.equal(
    rawColumnOrderPageLayout.blocks.some((block) => /Left column first line.*Right column first line/.test(block.text)),
    false,
  );
  assert.equal(rawColumnOrderPageLayout.blocks.some((block) => /arXiv:2409/.test(block.text)), false);
  assert.ok(rawColumnOrderPageText.indexOf('Left column second line') < rawColumnOrderPageText.indexOf('Right column first line'));

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
  assert.ok(landscapePageLayout.blocks[0].readingOrder < landscapePageLayout.blocks[1].readingOrder);

  const readableLayout = buildReadableTranslationLayout(
    pageLayout,
    [
      { id: pageLayout.blocks[0].id, translatedText: '语义对齐增强的代码翻译' },
      { id: pageLayout.blocks[1].id, translatedText: '这是第一段。' },
      { id: pageLayout.blocks[2].id, translatedText: '这是第二段。' },
    ],
  );
  assert.equal(readableLayout.sections.length >= 1, true);
  assert.equal(readableLayout.sections[0].items[0].role, 'title');
  assert.equal(readableLayout.summary.totalBlocks, 3);

  const readableTwoColumnLayout = buildReadableTranslationLayout(
    rawColumnOrderPageLayout,
    rawColumnOrderPageLayout.blocks.map((block) => ({ id: block.id, translatedText: `Translated ${block.text}` })),
  );
  const readableTwoColumnSection = readableTwoColumnLayout.sections.find((section) => section.type === 'columns');
  assert.ok(readableTwoColumnSection);
  assert.match(readableTwoColumnSection.left[0].translatedText, /Left column first line/);
  assert.match(readableTwoColumnSection.left[0].translatedText, /Left column second line/);
  assert.match(readableTwoColumnSection.right[0].translatedText, /Right column first line/);
  assert.match(readableTwoColumnSection.right[0].translatedText, /Right column second line/);

  const fidelityLayout = buildFidelityTranslationLayout(
    pageLayout,
    [
      { id: pageLayout.blocks[0].id, translatedText: '语义对齐增强的代码翻译' },
      { id: pageLayout.blocks[1].id, translatedText: '这是第一段。' },
      { id: pageLayout.blocks[2].id, translatedText: '这是第二段。' },
    ],
  );
  assert.ok(fidelityLayout);
  assert.equal(fidelityLayout.positionedItems[0].left, pageLayout.blocks[0].bbox.left);
  assert.equal(
    fidelityLayout.positionedItems[0].top,
    Number((pageLayout.blocks[0].bbox.top * (viewport.height / viewport.width)).toFixed(6)),
  );
  assert.equal(fidelityLayout.positionedItems[0].style.textAlign, 'center');

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
  const overflowLayout = buildFidelityTranslationLayout(twoColumnLayout, twoColumnTranslations, {
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
  const baselineGrowthLayout = buildFidelityTranslationLayout(pageGrowthLayout, pageGrowthTranslations);
  const expandedGrowthLayout = buildFidelityTranslationLayout(pageGrowthLayout, pageGrowthTranslations, {
    'growth-1': 1.2,
  });
  assert.ok(expandedGrowthLayout.pageHeight > baselineGrowthLayout.pageHeight);

  const emptyTextLayout = buildFidelityTranslationLayout(
    {
      viewport,
      blocks: [],
    },
  );
  assert.equal(emptyTextLayout, null);

  assert.equal(buildFidelityTranslationLayout({ blocks: [] }, twoColumnTranslations), null);

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

  const noisyTranslationLayout = buildTranslationRequestPageLayout({
    viewport,
    blocks: [
      {
        id: 'body',
        text: 'The ISAC BS senses a target.\nyk = gkHΦGx + gkHΦz0 + nk, k = 1, ... , K, (2)\nThe received echo is represented below.',
        bbox: { left: 0.08, top: 0.2, width: 0.4, height: 0.1 },
        style: { fontSize: 10, fontWeight: 'normal', italic: false },
      },
      {
        id: 'figure-label',
        text: 'Active RIS',
        bbox: { left: 0.2, top: 0.16, width: 0.08, height: 0.02 },
        style: { fontSize: 5, fontWeight: 'normal', italic: false },
      },
      {
        id: 'formula',
        text: 'SINRc,k ≥ γth,k, ∀k',
        bbox: { left: 0.58, top: 0.66, width: 0.25, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'footer',
        text: 'Authorized licensed use limited to: Nanjing University. Downloaded on April 28,2026 from IEEE Xplore. Restrictions apply.',
        bbox: { left: 0.1, top: 0.96, width: 0.8, height: 0.02 },
        style: { fontSize: 7, fontWeight: 'normal', italic: false },
      },
    ],
  });
  assert.deepEqual(
    noisyTranslationLayout.blocks.map((block) => block.id),
    ['body'],
  );
  assert.match(noisyTranslationLayout.blocks[0].text, /The ISAC BS senses a target/);
  assert.match(noisyTranslationLayout.blocks[0].text, /received echo/);

  const controlAndOperatorLayout = buildTranslationRequestPageLayout({
    viewport,
    blocks: [
      {
        id: 'readable-prose',
        text: 'This paragraph remains available for translation.',
        bbox: { left: 0.08, top: 0.2, width: 0.4, height: 0.06 },
        style: { fontSize: 10, fontWeight: 'normal', italic: false },
      },
      {
        id: 'control-text',
        text: 'broken\u0007text',
        bbox: { left: 0.08, top: 0.3, width: 0.12, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'slash-bracket-formula',
        text: 'x/y + [z]',
        bbox: { left: 0.58, top: 0.4, width: 0.12, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
    ],
  });
  assert.deepEqual(controlAndOperatorLayout.blocks.map((block) => block.id), ['readable-prose']);

  const formulaCleanLayout = buildTranslationRequestPageLayout({
    viewport,
    blocks: [
      {
        id: 'definition',
        text: 'where sk CN(0,1) denotes the communication symbol\nfksk + frsr,\nThe received echo is represented below.',
        bbox: { left: 0.08, top: 0.2, width: 0.4, height: 0.1 },
        style: { fontSize: 10, fontWeight: 'normal', italic: false },
      },
      {
        id: 'constraint',
        text: 'PhiGfk2 + PhiGfr2 <= PARIS',
        bbox: { left: 0.58, top: 0.66, width: 0.25, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'sinr-label',
        text: 'SINRs',
        bbox: { left: 0.6, top: 0.54, width: 0.08, height: 0.02 },
        style: { fontSize: 8.5, fontWeight: 'normal', italic: false },
      },
    ],
  });
  assert.deepEqual(
    formulaCleanLayout.blocks.map((block) => block.id),
    ['definition'],
  );
  assert.match(formulaCleanLayout.blocks[0].text, /where sk CN/);
  assert.match(formulaCleanLayout.blocks[0].text, /received echo/);
  assert.doesNotMatch(formulaCleanLayout.blocks[0].text, /fksk/);
  assert.doesNotMatch(noisyTranslationLayout.blocks[0].text, /gkHΦGx/);

  const algorithmAndResidueLayout = buildTranslationRequestPageLayout({
    viewport,
    blocks: [
      {
        id: 'selected-body',
        text: 'In this section, simulation results verify the effectiveness of the algorithm.',
        bbox: { left: 0.08, top: 0.72, width: 0.41, height: 0.08 },
        style: { fontSize: 10, fontWeight: 'normal', italic: false },
      },
      {
        id: 'algorithm-heading',
        text: 'Algorithm 1 Proposed AO Algorithm to Solve Problem (P0). Inputs: G, gk, PBS.',
        bbox: { left: 0.51, top: 0.1, width: 0.41, height: 0.03 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'algorithm-line',
        text: '1: Initialize w, fk, ∀k, fr and Φ in a feasible region.',
        bbox: { left: 0.52, top: 0.16, width: 0.35, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'math-fragment',
        text: 'fkHGH',
        bbox: { left: 0.23, top: 0.36, width: 0.05, height: 0.02 },
        style: { fontSize: 8, fontWeight: 'normal', italic: false },
      },
      {
        id: 'unit-fragment',
        text: 'f | 1GHz',
        bbox: { left: 0.8, top: 0.4, width: 0.05, height: 0.02 },
        style: { fontSize: 9, fontWeight: 'normal', italic: false },
      },
      {
        id: 'sqrt-residue',
        text: '√The complex amplitude coefficient is modeled as η =',
        bbox: { left: 0.51, top: 0.44, width: 0.41, height: 0.02 },
        style: { fontSize: 10, fontWeight: 'normal', italic: false },
      },
      {
        id: 'leading-residue',
        text: '2 [5]. The target of interest is at a distance of 30m.',
        bbox: { left: 0.69, top: 0.46, width: 0.23, height: 0.02 },
        style: { fontSize: 8, fontWeight: 'normal', italic: false },
      },
    ],
  });
  assert.deepEqual(
    algorithmAndResidueLayout.blocks.map((block) => block.id),
    ['selected-body', 'sqrt-residue', 'leading-residue'],
  );
  assert.equal(algorithmAndResidueLayout.blocks[1].text, 'The complex amplitude coefficient is modeled as');
  assert.equal(algorithmAndResidueLayout.blocks[2].text, 'The target of interest is at a distance of 30m.');

  const complexTwoColumnTextContent = {
    items: [
      {
        str: 'III. Proposed Method',
        transform: [13, 0, 0, 13, 62, 704],
        width: 170,
        height: 13,
        fontName: 'Times-Bold',
      },
      {
        str: 'The left column introduces the beamforming design.',
        transform: [10, 0, 0, 10, 62, 676],
        width: 220,
        height: 10,
        fontName: 'Times-Roman',
      },
      {
        str: 'It preserves the source paragraph for translation.',
        transform: [10, 0, 0, 10, 62, 661],
        width: 215,
        height: 10,
        fontName: 'Times-Roman',
      },
      {
        str: 'A. Communication Model',
        transform: [11, 0, 0, 11, 62, 624],
        width: 155,
        height: 11,
        fontName: 'Times-Bold',
      },
      {
        str: 'The model defines the communication channel.',
        transform: [10, 0, 0, 10, 62, 604],
        width: 205,
        height: 10,
        fontName: 'Times-Roman',
      },
      {
        str: 'B. Radar Model',
        transform: [11, 0, 0, 11, 336, 704],
        width: 120,
        height: 11,
        fontName: 'Times-Bold',
      },
      {
        str: 'The radar echo is processed after the communication model.',
        transform: [10, 0, 0, 10, 336, 676],
        width: 232,
        height: 10,
        fontName: 'Times-Roman',
      },
      {
        str: 'Algorithm 1 Proposed AO Algorithm to Solve Problem (P0). Inputs: G, gk, PBS.',
        transform: [8, 0, 0, 8, 336, 628],
        width: 220,
        height: 8,
        fontName: 'Times-Roman',
      },
      {
        str: '1: Initialize w, fk, fr and Phi.',
        transform: [8, 0, 0, 8, 336, 614],
        width: 145,
        height: 8,
        fontName: 'Times-Roman',
      },
      {
        str: 'SINRc,k ≥ γth,k, ∀k',
        transform: [8, 0, 0, 8, 426, 420],
        width: 112,
        height: 8,
        fontName: 'Times-Roman',
      },
    ],
  };
  const { pageText: complexTwoColumnPageText, pageLayout: complexTwoColumnPageLayout } = buildPageLayout(
    complexTwoColumnTextContent,
    viewport,
  );
  assert.equal(complexTwoColumnPageLayout.columnMode, 'two-column');
  assert.ok(complexTwoColumnPageText.indexOf('A. Communication Model') < complexTwoColumnPageText.indexOf('B. Radar Model'));
  assert.equal(complexTwoColumnPageLayout.blocks.some((block) => /Algorithm 1/.test(block.text)), false);
  assert.equal(complexTwoColumnPageLayout.blocks.some((block) => /SINRc/.test(block.text)), false);
  assert.ok(complexTwoColumnPageLayout.blocks.some((block) => /left column introduces/.test(block.text)));
  assert.ok(complexTwoColumnPageLayout.blocks.some((block) => /radar echo is processed/.test(block.text)));

  const figureFormulaAndBodyLayout = buildTranslationRequestPageLayout(
    {
      viewport,
      blocks: [
        {
          id: 'body-before-figure',
          text: 'The proposed protocol remains stable in the mixed figure page.',
          bbox: { left: 0.08, top: 0.18, width: 0.4, height: 0.06 },
          style: { fontSize: 10, fontWeight: 'normal', italic: false },
        },
        {
          id: 'figure-caption',
          text: 'RIS controller',
          bbox: { left: 0.18, top: 0.14, width: 0.12, height: 0.02 },
          style: { fontSize: 6.5, fontWeight: 'normal', italic: false },
        },
        {
          id: 'equation-line',
          text: 'yk = gkHΦGx + gkHΦz0 + nk, k = 1, ... , K, (2)',
          bbox: { left: 0.54, top: 0.54, width: 0.32, height: 0.02 },
          style: { fontSize: 9, fontWeight: 'normal', italic: false },
        },
        {
          id: 'body-after-figure',
          text: 'The retained paragraph explains why the algorithm converges.',
          bbox: { left: 0.08, top: 0.66, width: 0.4, height: 0.06 },
          style: { fontSize: 10, fontWeight: 'normal', italic: false },
        },
      ],
    },
    [
      {
        type: 'figure',
        bbox: { left: 0.12, top: 0.1, width: 0.25, height: 0.22 },
      },
    ],
    4,
  );
  assert.deepEqual(
    figureFormulaAndBodyLayout.blocks.map((block) => block.id),
    ['body-after-figure'],
  );
  assert.equal(figureFormulaAndBodyLayout.excludedZonesVersion, 4);
  assert.match(figureFormulaAndBodyLayout.blocks[0].text, /retained paragraph/);

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
