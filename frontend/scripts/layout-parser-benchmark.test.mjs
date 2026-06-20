import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import {
  evaluatePageLayout,
  findAnchorOrder,
  loadPdfJs,
  resolveFixturePath,
  resolveStandardFontDataUrl,
  scoreReadingOrder,
} from './layout-parser-benchmark.mjs';

const viewport = { width: 600, height: 800 };
const textContent = {
  items: [
    { str: 'left first', transform: [12, 0, 0, 12, 40, 740], width: 120, height: 12, fontName: 'Times' },
    { str: 'right first', transform: [12, 0, 0, 12, 340, 740], width: 120, height: 12, fontName: 'Times' },
    { str: 'left second', transform: [12, 0, 0, 12, 40, 700], width: 120, height: 12, fontName: 'Times' },
    { str: 'right second', transform: [12, 0, 0, 12, 340, 700], width: 120, height: 12, fontName: 'Times' },
    { str: 'left third paragraph with enough text for column detection', transform: [12, 0, 0, 12, 40, 660], width: 220, height: 12, fontName: 'Times' },
    { str: 'right third paragraph with enough text for column detection', transform: [12, 0, 0, 12, 340, 660], width: 220, height: 12, fontName: 'Times' },
    { str: 'left fourth paragraph with enough text for column detection', transform: [12, 0, 0, 12, 40, 620], width: 220, height: 12, fontName: 'Times' },
    { str: 'right fourth paragraph with enough text for column detection', transform: [12, 0, 0, 12, 340, 620], width: 220, height: 12, fontName: 'Times' },
    { str: 'E = mc2', transform: [12, 0, 0, 12, 220, 400], width: 100, height: 12, fontName: 'Times' },
  ],
};

const run = async () => {
  const pdfjs = await loadPdfJs();
  assert.equal(pdfjs.version, '3.4.120');
  assert.equal(resolveStandardFontDataUrl().endsWith(path.sep), true);
  assert.equal(fs.existsSync(resolveStandardFontDataUrl()), true);
  const pageLayout = {
    blocks: [
      { id: 'b2', text: 'second anchor', readingOrder: 1 },
      { id: 'b1', text: 'first anchor', readingOrder: 0 },
    ],
  };
  assert.deepEqual(findAnchorOrder(pageLayout, ['first anchor', 'second anchor']), ['first anchor', 'second anchor']);

  assert.deepEqual(scoreReadingOrder(['a', 'c', 'b'], ['a', 'b', 'c']), {
    goldAnchors: 3,
    matchedAnchors: 3,
    comparablePairs: 3,
    correctPairs: 2,
    accuracy: 2 / 3,
  });
  assert.equal(
    resolveFixturePath('C:/repo/benchmarks/layout/fixtures.json', 'paper.pdf', '../../../..'),
    path.resolve('C:/paper.pdf'),
  );

  const result = evaluatePageLayout({
    textContent,
    viewport,
    gold: {
      anchors: ['left first', 'left second', 'right first', 'right second'],
      bodyAnchors: ['left first'],
      formulaPatterns: ['E = mc2'],
    },
    excludedZones: [{ type: 'formula', bbox: { left: 0.3, top: 0.45, width: 0.4, height: 0.15 } }],
  });

  assert.equal(result.columnMode, 'two-column');
  assert.equal(result.failures.missingAnchors, 0);
  assert.equal(result.failures.readingOrderInversions, 0);
  assert.equal(result.failures.bodyFalseRemovals, 0);
  assert.equal(result.failures.formulaResiduals, 0);
};

await run();
console.log('layout parser benchmark tests passed');
