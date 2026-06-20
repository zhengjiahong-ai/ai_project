import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildPageLayout,
  buildTranslationRequestPageLayout,
} from '../src/utils/pdfTranslationLayout.js';

const normalizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();

export const findAnchorOrder = (pageLayout, anchors = []) => {
  const normalizedAnchors = anchors.map((anchor) => ({ raw: anchor, normalized: normalizeText(anchor) }));
  const blocks = [...(pageLayout?.blocks || [])].sort(
    (left, right) => Number(left?.readingOrder ?? Number.MAX_SAFE_INTEGER) - Number(right?.readingOrder ?? Number.MAX_SAFE_INTEGER),
  );

  return blocks.reduce((ordered, block) => {
    const text = normalizeText(block?.text);
    for (const anchor of normalizedAnchors) {
      if (!ordered.includes(anchor.raw) && text.includes(anchor.normalized)) {
        ordered.push(anchor.raw);
      }
    }
    return ordered;
  }, []);
};

export const scoreReadingOrder = (predicted = [], gold = []) => {
  const positions = new Map(predicted.map((anchor, index) => [anchor, index]));
  const shared = gold.filter((anchor) => positions.has(anchor));
  let correctPairs = 0;
  let comparablePairs = 0;
  for (let left = 0; left < shared.length; left += 1) {
    for (let right = left + 1; right < shared.length; right += 1) {
      comparablePairs += 1;
      if (positions.get(shared[left]) < positions.get(shared[right])) {
        correctPairs += 1;
      }
    }
  }
  return {
    goldAnchors: gold.length,
    matchedAnchors: shared.length,
    comparablePairs,
    correctPairs,
    accuracy: comparablePairs ? correctPairs / comparablePairs : 0,
  };
};

export const resolveFixturePath = (manifestPath, fixturePath, workspaceRoot = '.') =>
  path.resolve(path.dirname(manifestPath), workspaceRoot, fixturePath);

export const resolveStandardFontDataUrl = () =>
  `${path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../node_modules/pdfjs-dist/standard_fonts')}${path.sep}`;

const includesAnchor = (blocks, anchor) => {
  const needle = normalizeText(anchor);
  return blocks.some((block) => normalizeText(block?.text).includes(needle));
};

export const evaluatePageLayout = ({ textContent, viewport, gold = {}, excludedZones = [] }) => {
  const { pageLayout } = buildPageLayout(textContent, viewport);
  const requestLayout = buildTranslationRequestPageLayout(pageLayout, excludedZones, 1);
  const anchors = Array.isArray(gold.anchors) ? gold.anchors : [];
  const predictedOrder = findAnchorOrder(pageLayout, anchors);
  const readingOrder = scoreReadingOrder(predictedOrder, anchors);
  const bodyAnchors = Array.isArray(gold.bodyAnchors) ? gold.bodyAnchors : [];
  const formulaPatterns = Array.isArray(gold.formulaPatterns) ? gold.formulaPatterns : [];

  return {
    columnMode: pageLayout.columnMode,
    sourceBlockCount: pageLayout.blocks.length,
    requestBlockCount: requestLayout.blocks.length,
    predictedOrder,
    readingOrder,
    failures: {
      missingAnchors: anchors.length - predictedOrder.length,
      readingOrderInversions: readingOrder.comparablePairs - readingOrder.correctPairs,
      bodyFalseRemovals: bodyAnchors.filter(
        (anchor) => includesAnchor(pageLayout.blocks, anchor) && !includesAnchor(requestLayout.blocks, anchor),
      ).length,
      formulaResiduals: formulaPatterns.filter((pattern) => includesAnchor(requestLayout.blocks, pattern)).length,
      crossColumnSerializations:
        pageLayout.columnMode === 'two-column'
          ? readingOrder.comparablePairs - readingOrder.correctPairs
          : 0,
    },
  };
};

export const loadPdfJs = async () => {
  const module = await import('pdfjs-dist/build/pdf.js');
  return module.default || module;
};

export const evaluatePdfDocument = async ({ pdfPath, goldPages = [], excludedZonesByPage = {} }) => {
  const pdfjs = await loadPdfJs();
  const data = new Uint8Array(await fs.readFile(pdfPath));
  const document = await pdfjs.getDocument({
    data,
    disableWorker: true,
    standardFontDataUrl: resolveStandardFontDataUrl(),
  }).promise;
  const pageResults = [];
  const startedAt = performance.now();

  for (const annotation of goldPages) {
    const pageIndex = Number(annotation.pageIndex);
    const page = await document.getPage(pageIndex + 1);
    const viewport = page.getViewport({ scale: 1 });
    const textContent = await page.getTextContent();
    pageResults.push({
      pageIndex,
      ...evaluatePageLayout({
        textContent,
        viewport,
        gold: annotation,
        excludedZones: excludedZonesByPage[String(pageIndex)] || excludedZonesByPage[pageIndex] || [],
      }),
    });
  }

  return {
    status: 'success',
    pageCount: document.numPages,
    annotatedPageCount: pageResults.length,
    durationMs: Math.round(performance.now() - startedAt),
    pages: pageResults,
  };
};

const main = async () => {
  const [, , manifestPath, outputPath, grobidResultsPath] = process.argv;
  if (!manifestPath || !outputPath) {
    throw new Error('Usage: node layout-parser-benchmark.mjs <manifest.json> <output.json> [grobid-results.json]');
  }

  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  const grobidResults = grobidResultsPath
    ? JSON.parse(await fs.readFile(grobidResultsPath, 'utf8'))
    : { documents: [] };
  const grobidById = new Map((grobidResults.documents || []).map((item) => [item.id, item]));
  const documents = [];

  for (const item of manifest.documents || []) {
    const resolvedPath = resolveFixturePath(manifestPath, item.path, manifest.workspaceRoot);
    try {
      await fs.access(resolvedPath);
      documents.push({
        id: item.id,
        ...(await evaluatePdfDocument({
          pdfPath: resolvedPath,
          goldPages: item.gold?.pages || [],
          excludedZonesByPage: grobidById.get(item.id)?.excludedZonesByPage || {},
        })),
      });
    } catch (error) {
      documents.push({ id: item.id, status: 'missing_or_unreadable', error: String(error?.message || error), pages: [] });
    }
  }

  await fs.writeFile(
    outputPath,
    `${JSON.stringify({ schemaVersion: '1.0', runtime: { node: process.version, pdfjs: pdfjsVersion() }, documents }, null, 2)}\n`,
    'utf8',
  );
};

const pdfjsVersion = () => {
  try {
    return '3.4.120';
  } catch {
    return 'unknown';
  }
};

const isEntrypoint = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (isEntrypoint) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
