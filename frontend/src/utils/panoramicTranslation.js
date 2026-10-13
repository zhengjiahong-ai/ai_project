import { buildTranslationRequestPageLayout, normalizeRelativeBbox } from './pdfTranslationLayout.js';

export const hasMath = text => /[=∈∑∏Σαβγ√^]|\bR(?:\d|\()|\\(?:frac|sum|prod)\b/.test(text || '');

export function usesUnpositionedTranslation(pageLayout, translatedBlocks = []) {
  if (!pageLayout?.blocks?.length || !translatedBlocks.length) return true;
  const sourceIds = new Set(pageLayout.blocks.map(block => block.id));
  return !translatedBlocks.some(block => sourceIds.has(block.id));
}

/** Reflow translated paragraphs while retaining every intervening PDF region. */
export function buildPanoramicTranslation(pageLayout, translatedBlocks = [], excludedZones = []) {
  if (!pageLayout?.blocks?.length) return null;
  const accepted = new Set(buildTranslationRequestPageLayout(pageLayout, excludedZones).blocks.map(block => block.id));
  const translations = new Map(translatedBlocks.filter(block => accepted.has(block.id) && block.translatedText?.trim())
    .map(block => [block.id, block.translatedText]));
  const items = pageLayout.blocks.map(block => ({ ...block, bbox: normalizeRelativeBbox(block.bbox),
    translatedText: translations.get(block.id), preserveMath: hasMath(block.text) }))
    .filter(item => item.translatedText && item.bbox.width > 0 && item.bbox.height > 0)
    .sort((a, b) => a.bbox.top - b.bbox.top || a.bbox.left - b.bbox.left);
  const twoColumns = pageLayout.columnMode === 'two-column';
  const fullItems = twoColumns ? items.filter(item => {
    const box = item.bbox;
    return box.width >= 0.62 || (box.left < 0.46 && box.left + box.width > 0.54 &&
      Math.abs(box.left + box.width / 2 - 0.5) <= 0.12 && box.width >= 0.34);
  }) : [];
  const fullIds = new Set(fullItems.map(item => item.id));
  // Extracted line boxes end on the baseline; include descenders when replacing/cropping text.
  const descender = item => Math.min(4, Number(item.style?.fontSize || 0) * 0.25) /
    Math.max(1, Number(pageLayout.viewport?.height || 800));
  const bottom = item => Math.min(1, item.bbox.top + item.bbox.height + descender(item));
  const used = new Set();
  const sections = [];
  const source = (left, top, width, height) => ({ kind: 'source',
    bbox: { left, top, width, height }, id: `source-${left}-${top}-${height}` });
  const paragraph = item => ({ kind: 'translation', ...item,
    bbox: {...item.bbox,height:bottom(item)-item.bbox.top} });

  const appendBand = (start, end) => {
    if (end <= start) return;
    const band = items.filter(item => !fullIds.has(item.id) && !used.has(item.id) && item.bbox.top < end);
    if (!band.length) {
      sections.push({ type: 'full', items: [source(0, start, 1, end - start)] });
      return;
    }
    const firstTop = Math.min(...band.map(item => item.bbox.top));
    if (firstTop > start) {
      sections.push({ type: 'full', items: [source(0, start, 1, firstTop - start)] });
      start = firstTop;
    }
    const makeLane = (left, width, laneItems) => {
      const lane = [];
      let cursor = start;
      for (const item of laneItems) {
        used.add(item.id);
        if (item.bbox.top > cursor) lane.push(source(left, cursor, width, item.bbox.top - cursor));
        lane.push(paragraph(item));
        cursor = Math.max(cursor, bottom(item));
      }
      if (cursor < end) lane.push(source(left, cursor, width, end - cursor));
      return lane;
    };
    if (twoColumns) {
      sections.push({ type: 'columns', left: makeLane(0, 0.5, band.filter(item => item.bbox.left + item.bbox.width / 2 < 0.5)),
        right: makeLane(0.5, 0.5, band.filter(item => item.bbox.left + item.bbox.width / 2 >= 0.5)) });
    } else {
      sections.push({ type: 'full', items: makeLane(0, 1, band) });
    }
  };
  let cursor = 0;
  for (const item of fullItems) {
    appendBand(cursor, item.bbox.top);
    sections.push({ type: 'full', items: [paragraph(item)] });
    used.add(item.id);
    cursor = Math.max(cursor, bottom(item));
  }
  appendBand(cursor, 1);
  // In malformed/overlapping PDF geometry, never silently lose a completed paragraph.
  const remaining = items.filter(item => !used.has(item.id));
  if (remaining.length) sections.push({ type: 'full', items: remaining.map(paragraph) });
  return { sections, translatedCount: items.length, columnMode: twoColumns ? 'two-column' : 'single-column' };
}

/** Convert a normalized PDF region into a bounded source-pixel rectangle. */
export function sourcePixelRect(bbox, width, height) {
  const box = normalizeRelativeBbox(bbox);
  const x = Math.floor(box.left * width);
  const y = Math.floor(box.top * height);
  return { x, y, width: Math.max(0, Math.min(width - x, Math.ceil(box.width * width))),
    height: Math.max(0, Math.min(height - y, Math.ceil(box.height * height))) };
}
