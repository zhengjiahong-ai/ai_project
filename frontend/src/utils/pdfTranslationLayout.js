const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

const toFiniteNumber = (value, fallback = 0) => {
  const nextValue = Number(value);
  return Number.isFinite(nextValue) ? nextValue : fallback;
};

const roundRatio = (value) => Number(clamp(value).toFixed(6));

const CONTROL_TEXT_PATTERN = /[\u0000-\u001f\u007f\ufffd]/;
const TRANSLATION_FOOTER_PATTERN =
  /(?:authorized licensed use|downloaded on .* ieee xplore|restrictions apply|\$\d+(?:\.\d+)?|\u00a9\s*\d{4})/i;
const TRANSLATION_EQUATION_NUMBER_PATTERN = /^(?:\(?\d+[a-z]?\)?|\(\s*[A-Za-z]?\d+[a-z]?\s*\))$/i;
const TRANSLATION_MATH_SYMBOL_PATTERN =
  /[\u2200-\u22ff\u0391-\u03a9\u03b1-\u03c9\u03d1-\u03d6\u00b1\u00d7\u00f7\u00b2\u00b3\u2070-\u209f]/g;
const TRANSLATION_MATH_OPERATOR_PATTERN = /[=<>+\-*\/^_{}\[\](),;:|]/g;
const TRANSLATION_MATH_KEYWORD_PATTERN =
  /\b(?:argmax|argmin|diag|rank|sinrs?|snr|s\.t\.|subject\s+to|max|min|cn|tr)\b/gi;
const COMPACT_FORMULA_PATTERN =
  /(?:[A-Za-z]\w*\s*(?:[=<>+\-*\/^]|\bin\b)|(?:[=<>+\-*\/^]\s*[A-Za-z]\w*)|[A-Za-z]\([^)]*\)|\|\|[^|]+\|\|)/i;

const countMatches = (text, pattern) => (String(text || '').match(pattern) || []).length;

const countTranslationMathSignals = (text) =>
  countMatches(text, TRANSLATION_MATH_SYMBOL_PATTERN) +
  countMatches(text, TRANSLATION_MATH_OPERATOR_PATTERN) +
  countMatches(text, TRANSLATION_MATH_KEYWORD_PATTERN);

const countReadableWords = (text) =>
  countMatches(String(text || ''), /[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}/g);

const normalizeBlockSourceText = (text) => String(text || '').replace(/\s+/g, ' ').trim();

const isFooterText = (text) => TRANSLATION_FOOTER_PATTERN.test(normalizeBlockSourceText(text));

const isLikelyFigureLabelBlock = (text, block = {}) => {
  const value = normalizeBlockSourceText(text);
  if (!value) {
    return false;
  }

  const bbox = block?.bbox || {};
  const fontSize = Number(block?.style?.fontSize || 12);
  const isUpperLeftDiagramRegion =
    fontSize <= 8 &&
    (bbox.top || 0) >= 0.08 &&
    (bbox.top || 0) <= 0.3 &&
    (bbox.left || 0) < 0.5 &&
    (bbox.width || 0) <= 0.34;

  return isUpperLeftDiagramRegion && (value.length <= 90 || /^fig(?:ure)?\./i.test(value));
};

const isLikelyAlgorithmTableBlock = (text, block = {}) => {
  const value = normalizeBlockSourceText(text);
  if (!value) {
    return false;
  }

  const bbox = block?.bbox || {};
  const isUpperRightTableArea =
    (bbox.left || 0) >= 0.48 &&
    (bbox.top || 0) <= 0.36 &&
    (bbox.width || 0) <= 0.46;
  if (!isUpperRightTableArea) {
    return false;
  }

  return /(?:^Algorithm\s+\d+\b|\bInputs?\s*:|\bOutputs?\s*:|^\d+\s*:|\brepeat\b|\buntil\b|\breturn\b|\bUpdate\b|\bCalculate\b|\bInitialize\b|\biteration\b|\bfeasible region\b|\bmaximum number of iterations\b)/i.test(
    value,
  );
};

const stripFormulaResidueFromLine = (line) =>
  String(line || '')
    .replace(/^[\u221a√]\s*/, '')
    .replace(/^\d+\s*\[\d+\]\.\s*(?=[A-Z])/i, '')
    .replace(/\s+(?:[\u0391-\u03a9\u03b1-\u03c9A-Za-z][\w\u0391-\u03a9\u03b1-\u03c9]*)?\s*=\s*$/, '')
    .trim();

const isLikelyFormulaTextForTranslation = (text, block = {}) => {
  const value = normalizeBlockSourceText(text);
  if (!value) {
    return false;
  }

  if (TRANSLATION_EQUATION_NUMBER_PATTERN.test(value) || CONTROL_TEXT_PATTERN.test(value)) {
    return true;
  }

  const readableWords = countReadableWords(value);
  const mathSignals = countTranslationMathSignals(value);
  const hasCompactFormulaShape = COMPACT_FORMULA_PATTERN.test(value);
  const hasOptimizationLine = /^(?:\(?P\d+\)?\s*:|s\.t\.|subject\s+to|max|min)\b/i.test(value);
  const isWhereOnly = /^where$/i.test(value);
  const startsWithWhere = /^where\b/i.test(value);
  const hasDefinitionVerb = /\b(?:denotes?|represents?|is|are)\b/i.test(value);
  const bbox = block?.bbox || {};
  const fontSize = Number(block?.style?.fontSize || 12);
  const isShort = value.length <= 90;
  const isVeryShortOrphan =
    value.length <= 24 &&
    countReadableWords(value) <= 2 &&
    (bbox.width || 0) <= 0.16 &&
    !/[.!?]$/.test(value);
  const isBareMathIdentifier =
    value.length <= 18 &&
    !/\s/.test(value) &&
    /[A-Za-z]/.test(value) &&
    /(?:[a-z][A-Z]|[A-Z][a-z][A-Z]|[A-Za-z]\d|\d[A-Za-z])/.test(value);
  const isTinyStandaloneMath =
    fontSize <= 9.5 &&
    (bbox.width || 0) <= 0.24 &&
    value.length <= 48 &&
    readableWords <= 3 &&
    mathSignals >= 1;

  if (hasOptimizationLine) {
    return true;
  }

  if (isWhereOnly) {
    return true;
  }

  if (/^[A-Za-z]$/.test(value) || value === '.' || /^[A-Za-z]\s*\|\s*\d+\s*[A-Za-z]+$/i.test(value)) {
    return true;
  }

  if (isBareMathIdentifier) {
    return true;
  }

  if (isVeryShortOrphan && (bbox.top || 0) <= 0.16) {
    return true;
  }

  if (/^(?:represents?|denotes?)\b/i.test(value) && (bbox.left || 0) > 0.16 && (bbox.width || 0) <= 0.34) {
    return true;
  }

  if (/^[a-z]{2,}(?:tion|sion|ment|ing)?\.$/i.test(value) && value.length <= 24 && (bbox.width || 0) <= 0.16) {
    return true;
  }

  if ((startsWithWhere || hasDefinitionVerb) && readableWords >= 2 && ((bbox.width || 0) > 0.2 || value.length > 24)) {
    return false;
  }

  if (/^SINRs?$/i.test(value)) {
    return true;
  }

  if (isShort && readableWords <= 3 && mathSignals >= 3) {
    return true;
  }

  if (isShort && readableWords <= 2 && mathSignals >= 1) {
    return true;
  }

  if (isShort && readableWords <= 4 && mathSignals >= 2 && hasCompactFormulaShape) {
    return true;
  }

  if (value.length <= 180 && readableWords <= 4 && mathSignals >= 4 && hasCompactFormulaShape) {
    return true;
  }

  if (isTinyStandaloneMath && hasCompactFormulaShape) {
    return true;
  }

  return false;
};

const isLikelyNonTranslatableSourceBlock = (block = {}) => {
  const text = String(block?.text || '').trim();
  if (!text) {
    return true;
  }

  return (
    isFooterText(text) ||
    isLikelyFigureLabelBlock(text, block) ||
    isLikelyAlgorithmTableBlock(text, block) ||
    isLikelyFormulaTextForTranslation(text, block)
  );
};

const stripNonTranslatableLines = (text, block = {}) =>
  String(text || '')
    .split(/\n+/)
    .map((line) => line.trim())
    .map((line) => stripFormulaResidueFromLine(line))
    .filter((line) => line && !isFooterText(line) && !isLikelyFormulaTextForTranslation(line, block))
    .join('\n')
    .trim();

const inferFontSize = (item) => {
  const transform = item?.transform || [];
  const scaleX = Math.abs(toFiniteNumber(transform[0], 0));
  const scaleY = Math.abs(toFiniteNumber(transform[3], 0));
  const height = Math.abs(toFiniteNumber(item?.height, 0));
  return Math.max(scaleX, scaleY, height, 1);
};

const inferFontFlags = (item) => {
  const fontName = String(item?.fontName || '').toLowerCase();
  return {
    fontWeight:
      fontName.includes('bold') || fontName.includes('black') || fontName.includes('heavy') ? 'bold' : 'normal',
    italic: fontName.includes('italic') || fontName.includes('oblique'),
  };
};

const normalizeTextItem = (item, viewport) => {
  const text = typeof item?.str === 'string' ? item.str.replace(/\s+/g, ' ').trim() : '';
  if (!text) {
    return null;
  }

  const viewportWidth = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const viewportHeight = Math.max(toFiniteNumber(viewport?.height, 0), 1);
  const transform = item?.transform || [];
  const x = toFiniteNumber(transform?.[4], 0);
  const y = toFiniteNumber(transform?.[5], 0);
  const isRotatedMarginText =
    Math.abs(toFiniteNumber(transform?.[1], 0)) > Math.abs(toFiniteNumber(transform?.[0], 0)) + 1 &&
    Math.abs(toFiniteNumber(transform?.[2], 0)) > Math.abs(toFiniteNumber(transform?.[3], 0)) + 1 &&
    (x / viewportWidth < 0.08 || x / viewportWidth > 0.92);
  if (isRotatedMarginText) {
    return null;
  }
  const width = Math.max(toFiniteNumber(item?.width, 0), 1);
  const height = Math.max(Math.abs(toFiniteNumber(item?.height, 0)) || inferFontSize(item), 1);
  const fontSize = inferFontSize(item);
  const top = clamp((viewportHeight - y - height) / viewportHeight);
  const left = clamp(x / viewportWidth);
  const bboxWidth = clamp(width / viewportWidth);
  const bboxHeight = clamp(height / viewportHeight);

  return {
    text,
    x,
    y,
    width,
    height,
    fontSize,
    bbox: {
      left: roundRatio(left),
      top: roundRatio(top),
      width: roundRatio(bboxWidth),
      height: roundRatio(bboxHeight),
    },
    ...inferFontFlags(item),
  };
};

const buildLineText = (items = []) =>
  items
    .map((item, index) => {
      if (index === 0) {
        return item.text;
      }

      const previous = items[index - 1];
      const gap = item.x - (previous.x + previous.width);
      const insertSpace = gap > Math.max(previous.fontSize, item.fontSize) * 0.2;
      return `${insertSpace ? ' ' : ''}${item.text}`;
    })
    .join('')
    .trim();

const createLineBlock = (items = []) => {
  if (items.length === 0) {
    return null;
  }

  const sortedItems = [...items].sort((left, right) => left.x - right.x);
  const text = buildLineText(sortedItems);
  if (!text) {
    return null;
  }

  const left = Math.min(...sortedItems.map((item) => item.bbox.left));
  const top = Math.min(...sortedItems.map((item) => item.bbox.top));
  const right = Math.max(...sortedItems.map((item) => item.bbox.left + item.bbox.width));
  const bottom = Math.max(...sortedItems.map((item) => item.bbox.top + item.bbox.height));
  const fontSize =
    sortedItems.reduce((sum, item) => sum + item.fontSize, 0) / Math.max(sortedItems.length, 1);
  const boldCount = sortedItems.filter((item) => item.fontWeight === 'bold').length;
  const italicCount = sortedItems.filter((item) => item.italic).length;

  return {
    text,
    bbox: {
      left: roundRatio(left),
      top: roundRatio(top),
      width: roundRatio(right - left),
      height: roundRatio(bottom - top),
    },
    style: {
      fontSize: Number(fontSize.toFixed(2)),
      fontWeight: boldCount >= Math.ceil(sortedItems.length / 2) ? 'bold' : 'normal',
      italic: italicCount >= Math.ceil(sortedItems.length / 2),
    },
  };
};

const splitLineItemsIntoSegments = (items = [], viewport = {}) => {
  if (items.length <= 1) {
    return items.length ? [items] : [];
  }

  const sortedItems = [...items].sort((left, right) => left.x - right.x);
  const viewportWidth = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const segments = [];
  let currentSegment = [sortedItems[0]];

  for (let index = 1; index < sortedItems.length; index += 1) {
    const item = sortedItems[index];
    const previousItem = currentSegment[currentSegment.length - 1];
    const gap = item.x - (previousItem.x + previousItem.width);
    const previousCenter = (previousItem.x + previousItem.width / 2) / viewportWidth;
    const itemCenter = (item.x + item.width / 2) / viewportWidth;
    const isBodyText = Math.min(previousItem.bbox?.top || 0, item.bbox?.top || 0) >= 0.14;
    const crossesColumnGutter =
      isBodyText &&
      previousCenter < 0.48 &&
      itemCenter > 0.52 &&
      gap > Math.max(viewportWidth * 0.018, Math.max(previousItem.fontSize, item.fontSize) * 1.5);
    const threshold = Math.max(viewportWidth * 0.055, Math.max(previousItem.fontSize, item.fontSize) * 4);

    if (gap > threshold || crossesColumnGutter) {
      segments.push(currentSegment);
      currentSegment = [item];
      continue;
    }

    currentSegment.push(item);
  }

  if (currentSegment.length > 0) {
    segments.push(currentSegment);
  }

  return segments;
};

const getPageOrientation = (viewport = {}) => {
  const width = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const height = Math.max(toFiniteNumber(viewport?.height, 0), 1);
  return width > height ? 'landscape' : 'portrait';
};

const shouldMergeLine = (currentBlock, nextLine, viewport) => {
  if (!currentBlock || !nextLine) {
    return false;
  }

  const viewportWidth = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const viewportHeight = Math.max(toFiniteNumber(viewport?.height, 0), 1);
  const currentBottom = currentBlock.bbox.top + currentBlock.bbox.height;
  const verticalGap = (nextLine.bbox.top - currentBottom) * viewportHeight;
  const leftDiff = Math.abs(nextLine.bbox.left - currentBlock.bbox.left) * viewportWidth;
  const fontSizeDiff = Math.abs((nextLine.style?.fontSize || 0) - (currentBlock.style?.fontSize || 0));
  const currentText = String(currentBlock.text || '');
  const endsWithSentencePunctuation = /[.!?]$/.test(currentText);

  if (verticalGap > Math.max(currentBlock.style?.fontSize || 12, nextLine.style?.fontSize || 12) * 1.25) {
    return false;
  }

  if (leftDiff > Math.max(viewportWidth * 0.08, (currentBlock.style?.fontSize || 12) * 2.4)) {
    return false;
  }

  if (fontSizeDiff > 2.5) {
    return false;
  }

  if (endsWithSentencePunctuation && verticalGap > (currentBlock.style?.fontSize || 12) * 0.55) {
    return false;
  }

  return true;
};

const mergeLineIntoBlock = (currentBlock, nextLine) => {
  const left = Math.min(currentBlock.bbox.left, nextLine.bbox.left);
  const top = Math.min(currentBlock.bbox.top, nextLine.bbox.top);
  const right = Math.max(
    currentBlock.bbox.left + currentBlock.bbox.width,
    nextLine.bbox.left + nextLine.bbox.width,
  );
  const bottom = Math.max(
    currentBlock.bbox.top + currentBlock.bbox.height,
    nextLine.bbox.top + nextLine.bbox.height,
  );

  return {
    text: `${currentBlock.text}\n${nextLine.text}`.trim(),
    bbox: {
      left: roundRatio(left),
      top: roundRatio(top),
      width: roundRatio(right - left),
      height: roundRatio(bottom - top),
    },
    style: {
      fontSize: Number((((currentBlock.style?.fontSize || 0) + (nextLine.style?.fontSize || 0)) / 2).toFixed(2)),
      fontWeight:
        currentBlock.style?.fontWeight === 'bold' || nextLine.style?.fontWeight === 'bold' ? 'bold' : 'normal',
      italic: Boolean(currentBlock.style?.italic || nextLine.style?.italic),
    },
  };
};

const sortBlocksForReading = (blocks = []) =>
  [...blocks].sort((left, right) => {
    const leftOrder = Number.isFinite(Number(left?.readingOrder)) ? Number(left.readingOrder) : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(Number(right?.readingOrder))
      ? Number(right.readingOrder)
      : Number.MAX_SAFE_INTEGER;

    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }

    const topDiff = (left?.bbox?.top || 0) - (right?.bbox?.top || 0);
    if (Math.abs(topDiff) > 0.004) {
      return topDiff;
    }

    return (left?.bbox?.left || 0) - (right?.bbox?.left || 0);
  });

const getMedian = (values = [], fallback = 0) => {
  const numericValues = values
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);

  if (numericValues.length === 0) {
    return fallback;
  }

  const middleIndex = Math.floor(numericValues.length / 2);
  if (numericValues.length % 2 === 1) {
    return numericValues[middleIndex];
  }

  return (numericValues[middleIndex - 1] + numericValues[middleIndex]) / 2;
};

const detectTwoColumnCandidates = (items = []) => {
  const candidates = items.filter((item) => {
    const bbox = item?.bbox || {};
    const center = bbox.left + bbox.width / 2;
    const spansMiddle = bbox.left < 0.46 && bbox.left + bbox.width > 0.54;
    const isTrueFullWidth = spansMiddle && Math.abs(center - 0.5) <= 0.12 && bbox.width >= 0.34;
    return !isTrueFullWidth && bbox.width >= 0.12 && bbox.width <= 0.5 && bbox.top >= 0.14 && center >= 0.06 && center <= 0.94;
  });

  const leftCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 < 0.5);
  const rightCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 >= 0.5);
  const leftTop = leftCandidates.length > 0 ? Math.min(...leftCandidates.map((item) => item.bbox.top)) : 1;
  const rightTop = rightCandidates.length > 0 ? Math.min(...rightCandidates.map((item) => item.bbox.top)) : 1;
  const startsInSameBodyBand = Math.abs(leftTop - rightTop) <= 0.14;
  const hasStrongTwoColumnEvidence = leftCandidates.length >= 3 && rightCandidates.length >= 3;
  const enabled =
    leftCandidates.length >= 1 &&
    rightCandidates.length >= 1 &&
    (startsInSameBodyBand || hasStrongTwoColumnEvidence);

  return {
    candidates,
    leftCandidates,
    rightCandidates,
    enabled,
  };
};

const detectColumnLayout = (items = [], viewport = {}) => {
  const orientation = getPageOrientation(viewport);
  const columnDetection = detectTwoColumnCandidates(items);
  return {
    ...columnDetection,
    orientation,
    columnMode: columnDetection.enabled ? 'two-column' : 'single-column',
    bodyStartTop: columnDetection.enabled
      ? Math.min(...columnDetection.candidates.map((item) => item.bbox.top))
      : 1,
  };
};

const sortBlocksByGeometry = (blocks = []) =>
  [...blocks].sort((left, right) => {
    const topDiff = (left?.bbox?.top || 0) - (right?.bbox?.top || 0);
    if (Math.abs(topDiff) > 0.004) {
      return topDiff;
    }

    return (left?.bbox?.left || 0) - (right?.bbox?.left || 0);
  });

const buildLineBlocksFromOrderedItems = (orderedItems = [], viewport = {}) => {
  const lines = [];

  orderedItems.forEach((item) => {
    const currentLine = lines[lines.length - 1];
    if (!currentLine) {
      lines.push({ y: item.y, items: [item] });
      return;
    }

    const tolerance = Math.max(currentLine.items[0]?.height || 0, item.height) * 0.45 + 1.5;
    if (Math.abs(currentLine.y - item.y) <= tolerance) {
      currentLine.items.push(item);
      return;
    }

    lines.push({ y: item.y, items: [item] });
  });

  return lines
    .flatMap((line) => splitLineItemsIntoSegments(line.items, viewport))
    .map((segmentItems) => createLineBlock(segmentItems))
    .filter(Boolean);
};

const buildColumnFirstReadingOrder = (blocks = [], viewport = {}) => {
  const sortedBlocks = sortBlocksByGeometry(blocks);
  const columnLayout = detectColumnLayout(sortedBlocks, viewport);
  if (columnLayout.orientation !== 'portrait' || sortedBlocks.length < 2 || columnLayout.columnMode !== 'two-column') {
    return sortedBlocks;
  }

  const bodyStartTop = columnLayout.bodyStartTop;
  const headerBlocks = [];
  const bodyLeftBlocks = [];
  const bodyRightBlocks = [];
  const bodyFullBlocks = [];

  sortedBlocks.forEach((block) => {
    const placement = resolveItemPlacement(block, columnLayout, bodyStartTop);
    if (placement === 'full') {
      if ((block?.bbox?.top || 0) < bodyStartTop) {
        headerBlocks.push(block);
        return;
      }

      bodyFullBlocks.push(block);
      return;
    }

    if (placement === 'left') {
      bodyLeftBlocks.push(block);
      return;
    }

    bodyRightBlocks.push(block);
  });

  if (bodyLeftBlocks.length === 0 || bodyRightBlocks.length === 0) {
    return sortedBlocks;
  }

  const orderedBlocks = [...headerBlocks];
  let currentBandTop = 0;
  const consumedBlocks = new Set();

  const appendBandBlocks = (bandStart, bandEnd = Number.POSITIVE_INFINITY) => {
    bodyLeftBlocks.forEach((block) => {
      const top = block?.bbox?.top || 0;
      if (consumedBlocks.has(block) || top < bandStart || top >= bandEnd) {
        return;
      }

      orderedBlocks.push(block);
      consumedBlocks.add(block);
    });

    bodyRightBlocks.forEach((block) => {
      const top = block?.bbox?.top || 0;
      if (consumedBlocks.has(block) || top < bandStart || top >= bandEnd) {
        return;
      }

      orderedBlocks.push(block);
      consumedBlocks.add(block);
    });
  };

  bodyFullBlocks.forEach((block) => {
    const blockTop = block?.bbox?.top || 0;
    appendBandBlocks(currentBandTop, blockTop);
    orderedBlocks.push(block);
    currentBandTop = blockTop + 0.0001;
  });

  appendBandBlocks(currentBandTop);

  const remainingBlocks = sortedBlocks.filter((block) => !orderedBlocks.includes(block));
  return [...orderedBlocks, ...remainingBlocks];
};

const canMergeInColumnLayout = (currentBlock, nextLine, columnLayout) => {
  if (!columnLayout || columnLayout.orientation !== 'portrait' || columnLayout.columnMode !== 'two-column') {
    return true;
  }

  const bodyStartTop = columnLayout.bodyStartTop;
  const currentPlacement = resolveItemPlacement(currentBlock, columnLayout, bodyStartTop);
  const nextPlacement = resolveItemPlacement(nextLine, columnLayout, bodyStartTop);

  return currentPlacement === nextPlacement;
};

const mergeOrderedLineBlocks = (orderedLineBlocks = [], columnLayout = null, viewport = {}) =>
  orderedLineBlocks.reduce((blocks, lineBlock) => {
    const currentBlock = blocks[blocks.length - 1];
    if (
      canMergeInColumnLayout(currentBlock, lineBlock, columnLayout) &&
      shouldMergeLine(currentBlock, lineBlock, viewport)
    ) {
      blocks[blocks.length - 1] = mergeLineIntoBlock(currentBlock, lineBlock);
      return blocks;
    }

    blocks.push(lineBlock);
    return blocks;
  }, []);

const resolveReadableBlockRole = (block, medianFontSize, bodyStartTop) => {
  const fontSize = Number(block?.style?.fontSize || medianFontSize || 12);
  const bbox = block?.bbox || {};
  const textLength = String(block?.translatedText || block?.text || '').trim().length;
  const isNearTop = bbox.top <= Math.max(bodyStartTop * 0.9, 0.18);
  const isWide = bbox.width >= 0.5;
  const isShort = textLength > 0 && textLength <= 90;

  if ((fontSize >= medianFontSize + 5 && isWide) || (bbox.top <= 0.12 && fontSize >= medianFontSize + 3)) {
    return 'title';
  }

  if (isNearTop && (isWide || fontSize >= medianFontSize + 1)) {
    return 'meta';
  }

  if (isShort && (fontSize >= medianFontSize + 1.5 || block?.style?.fontWeight === 'bold')) {
    return 'heading';
  }

  return 'body';
};

const createReadableBlock = (block, medianFontSize, bodyStartTop) => ({
  ...block,
  kind: 'text',
  role: resolveReadableBlockRole(block, medianFontSize, bodyStartTop),
});

const resolveItemPlacement = (item, columnDetection, bodyStartTop) => {
  const bbox = item?.bbox || {};
  const spansMiddle = bbox.left < 0.46 && bbox.left + bbox.width > 0.54;
  const center = bbox.left + bbox.width / 2;
  const isTrueFullWidth = spansMiddle && Math.abs(center - 0.5) <= 0.12 && bbox.width >= 0.34;
  const canUseColumns = columnDetection.enabled && bbox.width <= 0.58 && !isTrueFullWidth;

  if (!canUseColumns) {
    return 'full';
  }

  return center < 0.5 ? 'left' : 'right';
};

export const normalizeViewport = (viewport = {}) => {
  const width = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const height = Math.max(toFiniteNumber(viewport?.height, 0), 1);
  return { width: Number(width.toFixed(2)), height: Number(height.toFixed(2)) };
};

export const normalizeRelativeBbox = (bbox = {}) => ({
  left: roundRatio(toFiniteNumber(bbox?.left, 0)),
  top: roundRatio(toFiniteNumber(bbox?.top, 0)),
  width: roundRatio(toFiniteNumber(bbox?.width, 0)),
  height: roundRatio(toFiniteNumber(bbox?.height, 0)),
});

export const normalizeExcludedZones = (zones = []) =>
  Array.isArray(zones)
    ? zones
        .map((zone) => ({
          type: String(zone?.type || 'excluded'),
          bbox: normalizeRelativeBbox(zone?.bbox || {}),
        }))
        .filter((zone) => zone.bbox.width > 0 && zone.bbox.height > 0)
    : [];

export const doesBboxIntersect = (leftBox, rightBox) => {
  if (!leftBox || !rightBox) {
    return false;
  }

  return !(
    leftBox.left + leftBox.width <= rightBox.left ||
    rightBox.left + rightBox.width <= leftBox.left ||
    leftBox.top + leftBox.height <= rightBox.top ||
    rightBox.top + rightBox.height <= leftBox.top
  );
};

export const isBlockInExcludedZone = (block, excludedZones = []) =>
  normalizeExcludedZones(excludedZones).some((zone) => doesBboxIntersect(block?.bbox, zone.bbox));

export const buildReadableTranslationLayout = (pageLayout, translatedBlocks = []) => {
  const translatedBlockMap = new Map(
    (Array.isArray(translatedBlocks) ? translatedBlocks : [])
      .map((block) => ({
        id: String(block?.id || '').trim(),
        translatedText: String(block?.translatedText || '').trim(),
      }))
      .filter((block) => block.id && block.translatedText)
      .map((block) => [block.id, block.translatedText]),
  );

  const sourceBlocks = Array.isArray(pageLayout?.blocks) ? sortBlocksForReading(pageLayout.blocks) : [];
  const translatedLayoutBlocks = sourceBlocks
    .map((block) => ({
      ...block,
      translatedText: translatedBlockMap.get(block.id) || '',
    }))
    .filter((block) => block.translatedText);

  if (translatedLayoutBlocks.length === 0) {
    return null;
  }

  const medianFontSize = getMedian(
    translatedLayoutBlocks.map((block) => Number(block?.style?.fontSize || 12)),
    12,
  );
  const viewport = pageLayout?.viewport ? normalizeViewport(pageLayout.viewport) : normalizeViewport({ width: 1, height: 1 });
  const columnDetection = detectColumnLayout(translatedLayoutBlocks, viewport);
  const bodyStartTop = columnDetection.bodyStartTop;

  const contentItems = [
    ...translatedLayoutBlocks.map((block) => createReadableBlock(block, medianFontSize, bodyStartTop)),
  ].sort((left, right) => {
    const leftOrder = Number.isFinite(Number(left?.readingOrder)) ? Number(left.readingOrder) : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(Number(right?.readingOrder))
      ? Number(right.readingOrder)
      : Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }

    const topDiff = (left?.bbox?.top || 0) - (right?.bbox?.top || 0);
    if (Math.abs(topDiff) > 0.004) {
      return topDiff;
    }

    return (left?.bbox?.left || 0) - (right?.bbox?.left || 0);
  });

  const sections = [];
  let currentColumnSection = null;

  const flushColumnSection = () => {
    if (!currentColumnSection) {
      return;
    }

    const hasItems = currentColumnSection.left.length > 0 || currentColumnSection.right.length > 0;
    if (hasItems) {
      sections.push(currentColumnSection);
    }
    currentColumnSection = null;
  };

  contentItems.forEach((item) => {
    const placement = resolveItemPlacement(item, columnDetection, bodyStartTop);

    if (placement === 'full') {
      flushColumnSection();
      sections.push({
        type: 'full',
        items: [item],
      });
      return;
    }

    if (!currentColumnSection) {
      currentColumnSection = {
        type: 'columns',
        left: [],
        right: [],
      };
    }

    currentColumnSection[placement].push(item);
  });

  flushColumnSection();

  if (sections.length === 0) {
    return null;
  }

  return {
    viewport,
    orientation: columnDetection.orientation,
    columnMode: columnDetection.columnMode,
    mode: columnDetection.columnMode,
    sections,
    summary: {
      totalBlocks: translatedLayoutBlocks.length,
      bodyStartTop: columnDetection.enabled ? roundRatio(bodyStartTop) : null,
    },
  };
};

const normalizeMeasuredHeightMap = (measuredHeightUnits = {}) =>
  Object.entries(measuredHeightUnits || {}).reduce((accumulator, [itemId, value]) => {
    const normalizedValue = Number(value);
    if (itemId && Number.isFinite(normalizedValue) && normalizedValue > 0) {
      accumulator[itemId] = normalizedValue;
    }
    return accumulator;
  }, {});

const getPageAspectRatio = (viewport = {}) => {
  const width = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const height = Math.max(toFiniteNumber(viewport?.height, 0), 1);
  return height / width;
};

const toPageWidthUnits = (bbox = {}, pageAspectRatio = 1) => ({
  left: roundRatio(toFiniteNumber(bbox?.left, 0)),
  top: Number((toFiniteNumber(bbox?.top, 0) * pageAspectRatio).toFixed(6)),
  width: roundRatio(toFiniteNumber(bbox?.width, 0)),
  height: Number((toFiniteNumber(bbox?.height, 0) * pageAspectRatio).toFixed(6)),
});

const resolveLayoutLane = (bbox = {}) => {
  const left = toFiniteNumber(bbox?.left, 0);
  const width = toFiniteNumber(bbox?.width, 0);
  const center = left + width / 2;

  if (width >= 0.62 || (width >= 0.52 && Math.abs(center - 0.5) <= 0.12)) {
    return 'full';
  }

  return center < 0.5 ? 'left' : 'right';
};

const applyColumnFrame = (frame, lane, columnLayout) => {
  if (columnLayout?.orientation !== 'portrait' || columnLayout?.columnMode !== 'two-column') {
    return frame;
  }

  if (lane !== 'left' && lane !== 'right') {
    return frame;
  }

  const columnLeft = lane === 'left' ? 0.08 : 0.54;
  const columnRight = lane === 'left' ? 0.48 : 0.94;
  const nextLeft = Math.max(frame.left, columnLeft);
  const nextRight = Math.min(frame.left + frame.width, columnRight);

  return {
    ...frame,
    left: Number(nextLeft.toFixed(6)),
    width: Number(Math.max(0.16, nextRight - nextLeft).toFixed(6)),
  };
};

const resolveBlockTextAlign = (block = {}) => {
  const declaredAlign = String(block?.style?.textAlign || 'left').toLowerCase();
  if (declaredAlign === 'center' || declaredAlign === 'right' || declaredAlign === 'justify') {
    return declaredAlign;
  }

  const bbox = block?.bbox || {};
  const center = bbox.left + bbox.width / 2;
  const isCentered = Math.abs(center - 0.5) <= 0.1;
  const isNearTop = bbox.top <= 0.22;
  const isWide = bbox.width >= 0.36;

  return isCentered && isNearTop && isWide ? 'center' : 'left';
};

const sortPositionedItems = (items = []) =>
  [...items].sort((left, right) => {
    const leftOrder = Number.isFinite(Number(left?.readingOrder)) ? Number(left.readingOrder) : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(Number(right?.readingOrder))
      ? Number(right.readingOrder)
      : Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }

    const topDiff = (left?.frame?.top || 0) - (right?.frame?.top || 0);
    if (Math.abs(topDiff) > 0.004) {
      return topDiff;
    }

    return (left?.frame?.left || 0) - (right?.frame?.left || 0);
  });

const doesHorizontalRangeOverlap = (leftItem, rightItem) =>
  !(
    (leftItem?.left || 0) + (leftItem?.width || 0) <= (rightItem?.frame?.left || 0) ||
    (rightItem?.frame?.left || 0) + (rightItem?.frame?.width || 0) <= (leftItem?.left || 0)
  );

const getSafeVerticalGapUnits = (item, viewport = {}) => {
  const viewportWidth = Math.max(toFiniteNumber(viewport?.width, 0), 1);
  const fontSize = toFiniteNumber(item?.style?.fontSize, 12);
  return Number(Math.max(0.012, fontSize / viewportWidth).toFixed(6));
};

export const buildFidelityTranslationLayout = (
  pageLayout,
  translatedBlocks = [],
  measuredHeightUnits = {},
) => {
  const rawViewportWidth = Number(pageLayout?.viewport?.width || 0);
  const rawViewportHeight = Number(pageLayout?.viewport?.height || 0);
  if (!Number.isFinite(rawViewportWidth) || !Number.isFinite(rawViewportHeight) || rawViewportWidth <= 1 || rawViewportHeight <= 1) {
    return null;
  }

  const viewport = normalizeViewport(pageLayout.viewport);
  const pageAspectRatio = getPageAspectRatio(viewport);
  const normalizedMeasuredHeights = normalizeMeasuredHeightMap(measuredHeightUnits);
  const translatedBlockMap = new Map(
    (Array.isArray(translatedBlocks) ? translatedBlocks : [])
      .map((block) => ({
        id: String(block?.id || '').trim(),
        translatedText: String(block?.translatedText || '').trim(),
      }))
      .filter((block) => block.id && block.translatedText)
      .map((block) => [block.id, block.translatedText]),
  );

  const sourceBlocks = Array.isArray(pageLayout?.blocks) ? sortBlocksForReading(pageLayout.blocks) : [];
  const columnLayout = detectColumnLayout(sourceBlocks, viewport);
  const textItems = sourceBlocks
    .map((block) => {
      const translatedText = translatedBlockMap.get(block.id) || '';
      if (!translatedText) {
        return null;
      }

      const lane = resolveLayoutLane(block.bbox);
      const frame = applyColumnFrame(toPageWidthUnits(block.bbox, pageAspectRatio), lane, columnLayout);
      return {
        id: block.id,
        kind: 'text',
        translatedText,
        readingOrder: Number.isFinite(Number(block?.readingOrder)) ? Number(block.readingOrder) : Number.MAX_SAFE_INTEGER,
        lane,
        frame,
        bbox: normalizeRelativeBbox(block.bbox || {}),
        style: {
          fontSize: toFiniteNumber(block?.style?.fontSize, 12),
          fontWeight: block?.style?.fontWeight === 'bold' ? 'bold' : 'normal',
          italic: Boolean(block?.style?.italic),
          textAlign: resolveBlockTextAlign(block),
        },
      };
    })
    .filter(Boolean);

  const sourceItems = sortPositionedItems(textItems);
  if (sourceItems.length === 0) {
    return null;
  }

  const positionedItems = sourceItems.reduce((accumulator, item) => {
    const baseHeight = Math.max(toFiniteNumber(item?.frame?.height, 0), 0.018);
    const resolvedHeight = Math.max(baseHeight, toFiniteNumber(normalizedMeasuredHeights[item.id], 0));

    const gap = getSafeVerticalGapUnits(item, viewport);
    const nextTop = accumulator.reduce((resolvedTop, previousItem) => {
      const lanePush = previousItem.lane === 'full' || previousItem.lane === item.lane;
      const overlapPush = doesHorizontalRangeOverlap(previousItem, item);
      if (!lanePush && !overlapPush) {
        return resolvedTop;
      }

      return Math.max(resolvedTop, previousItem.top + previousItem.height + Math.max(previousItem.gap, gap));
    }, item.frame.top);

    accumulator.push({
      ...item,
      left: item.frame.left,
      top: Number(nextTop.toFixed(6)),
      width: item.frame.width,
      height: Number(resolvedHeight.toFixed(6)),
      baseTop: item.frame.top,
      baseHeight,
      gap,
    });

    return accumulator;
  }, []);

  const bottomPadding = Math.max(0.04, Number((24 / Math.max(viewport.width, 1)).toFixed(6)));
  const pageHeight = Number(
    Math.max(
      pageAspectRatio,
      ...positionedItems.map((item) => item.top + item.height + bottomPadding),
    ).toFixed(6),
  );

  return {
    viewport,
    orientation: columnLayout.orientation,
    columnMode: columnLayout.columnMode,
    pageAspectRatio: Number(pageAspectRatio.toFixed(6)),
    pageHeight,
    positionedItems,
    summary: {
      totalBlocks: textItems.length,
      overflowItems: positionedItems.filter((item) => item.height > item.baseHeight + 0.001).length,
    },
  };
};

export const buildPageLayout = (textContent, viewport) => {
  const normalizedViewport = normalizeViewport(viewport);
  const items = (textContent?.items || [])
    .map((item) => normalizeTextItem(item, normalizedViewport))
    .filter(Boolean);

  if (items.length === 0) {
    return {
      pageText: '',
      pageLayout: {
        viewport: normalizedViewport,
        orientation: getPageOrientation(normalizedViewport),
        columnMode: 'single-column',
        blocks: [],
      },
    };
  }

  const rawLineBlocks = buildLineBlocksFromOrderedItems(items, normalizedViewport);
  const rawColumnLayout = detectColumnLayout(rawLineBlocks, normalizedViewport);
  const shouldUseRawColumnOrder =
    rawColumnLayout.orientation === 'portrait' && rawColumnLayout.columnMode === 'two-column';

  const sortedItems = shouldUseRawColumnOrder
    ? []
    : [...items].sort((left, right) => {
        if (Math.abs(left.y - right.y) > Math.max(left.height, right.height) * 0.4) {
          return right.y - left.y;
        }

        return left.x - right.x;
      });

  const lineBlocks = shouldUseRawColumnOrder
    ? rawLineBlocks
    : buildLineBlocksFromOrderedItems(sortedItems, normalizedViewport);
  const rawLineColumnLayout = shouldUseRawColumnOrder
    ? rawColumnLayout
    : detectColumnLayout(lineBlocks, normalizedViewport);
  const rawOrderedLineBlocks = buildColumnFirstReadingOrder(lineBlocks, normalizedViewport);
  const rawBlocks = mergeOrderedLineBlocks(rawOrderedLineBlocks, rawLineColumnLayout, normalizedViewport);
  const rawPageText = rawBlocks.map((block) => block.text).join('\n\n').trim();
  const filteredLineBlocks = lineBlocks.filter((block) => !isLikelyNonTranslatableSourceBlock(block));
  const layoutLineBlocks = filteredLineBlocks.length > 0 ? filteredLineBlocks : lineBlocks;
  const lineColumnLayout = shouldUseRawColumnOrder ? rawColumnLayout : detectColumnLayout(layoutLineBlocks, normalizedViewport);
  const orderedLineBlocks = buildColumnFirstReadingOrder(layoutLineBlocks, normalizedViewport);
  const blocks = mergeOrderedLineBlocks(orderedLineBlocks, lineColumnLayout, normalizedViewport);

  const finalizedBlocks = blocks.map((block, index) => ({
    id: `block-${index + 1}`,
    text: block.text,
    bbox: block.bbox,
    style: {
      ...block.style,
      textAlign: 'left',
    },
    readingOrder: index,
  }));

  return {
    pageText: rawPageText,
    pageLayout: {
      viewport: normalizedViewport,
      orientation: lineColumnLayout.orientation,
      columnMode: lineColumnLayout.columnMode,
      blocks: finalizedBlocks,
    },
  };
};

export const buildTranslationRequestPageLayout = (pageLayout, excludedZones = [], excludedZonesVersion = 1) => {
  const viewport = normalizeViewport(pageLayout?.viewport || {});
  const blocks = Array.isArray(pageLayout?.blocks)
    ? pageLayout.blocks
        .map((block) => {
          const normalizedBlock = {
            id: String(block?.id || '').trim(),
            text: String(block?.text || '').trim(),
            bbox: normalizeRelativeBbox(block?.bbox || {}),
            style: {
              fontSize: toFiniteNumber(block?.style?.fontSize, 12),
              fontWeight: block?.style?.fontWeight === 'bold' ? 'bold' : 'normal',
              italic: Boolean(block?.style?.italic),
              textAlign: String(block?.style?.textAlign || 'left'),
            },
          };
          return {
            ...normalizedBlock,
            text: stripNonTranslatableLines(normalizedBlock.text, normalizedBlock),
          };
        })
        .filter(
          (block) =>
            block.id &&
            block.text &&
            !isLikelyNonTranslatableSourceBlock(block) &&
            !isBlockInExcludedZone(block, excludedZones),
        )
    : [];

  return {
    viewport,
    blocks,
    excludedZonesVersion: toFiniteNumber(excludedZonesVersion, 1),
  };
};
