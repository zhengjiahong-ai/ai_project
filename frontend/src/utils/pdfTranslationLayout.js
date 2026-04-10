const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));

const toFiniteNumber = (value, fallback = 0) => {
  const nextValue = Number(value);
  return Number.isFinite(nextValue) ? nextValue : fallback;
};

const roundRatio = (value) => Number(clamp(value).toFixed(6));

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
  const x = toFiniteNumber(item?.transform?.[4], 0);
  const y = toFiniteNumber(item?.transform?.[5], 0);
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
    return !spansMiddle && bbox.width >= 0.16 && bbox.width <= 0.46 && bbox.top >= 0.16 && center >= 0.08 && center <= 0.92;
  });

  const leftCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 < 0.5);
  const rightCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 >= 0.5);

  return {
    candidates,
    leftCandidates,
    rightCandidates,
    enabled: leftCandidates.length >= 2 && rightCandidates.length >= 2,
  };
};

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
  const canUseColumns =
    columnDetection.enabled && bbox.top >= bodyStartTop && !spansMiddle && bbox.width <= 0.5;

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

export const normalizeFigureSnippets = (figureSnippets = []) =>
  Array.isArray(figureSnippets)
    ? figureSnippets
        .map((snippet, index) => ({
          id: String(snippet?.id || `figure-${index + 1}`),
          type: String(snippet?.type || 'figure'),
          bbox: normalizeRelativeBbox(snippet?.bbox || {}),
          image: typeof snippet?.image === 'string' ? snippet.image : '',
        }))
        .filter((snippet) => snippet.image && snippet.bbox.width > 0 && snippet.bbox.height > 0)
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

export const buildReadableTranslationLayout = (pageLayout, translatedBlocks = [], figureSnippets = []) => {
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

  const normalizedFigures = normalizeFigureSnippets(figureSnippets);
  if (translatedLayoutBlocks.length === 0 && normalizedFigures.length === 0) {
    return null;
  }

  const medianFontSize = getMedian(
    translatedLayoutBlocks.map((block) => Number(block?.style?.fontSize || 12)),
    12,
  );
  const textColumnDetection = detectTwoColumnCandidates(translatedLayoutBlocks);
  const figureColumnDetection = detectTwoColumnCandidates(normalizedFigures);
  const columnDetection = textColumnDetection.enabled ? textColumnDetection : figureColumnDetection;
  const bodyStartTop = columnDetection.enabled
    ? Math.min(...columnDetection.candidates.map((item) => item.bbox.top))
    : 1;

  const contentItems = [
    ...translatedLayoutBlocks.map((block) => createReadableBlock(block, medianFontSize, bodyStartTop)),
    ...normalizedFigures.map((figure, index) => ({
      ...figure,
      kind: 'figure',
      readingOrder: Number.MAX_SAFE_INTEGER / 4 + index,
    })),
  ].sort((left, right) => {
    const topDiff = (left?.bbox?.top || 0) - (right?.bbox?.top || 0);
    if (Math.abs(topDiff) > 0.004) {
      return topDiff;
    }

    const leftOrder = Number.isFinite(Number(left?.readingOrder)) ? Number(left.readingOrder) : Number.MAX_SAFE_INTEGER;
    const rightOrder = Number.isFinite(Number(right?.readingOrder))
      ? Number(right.readingOrder)
      : Number.MAX_SAFE_INTEGER;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
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
    viewport: pageLayout?.viewport ? normalizeViewport(pageLayout.viewport) : normalizeViewport({ width: 1, height: 1 }),
    mode: columnDetection.enabled ? 'two-column' : 'single-column',
    sections,
    summary: {
      totalBlocks: translatedLayoutBlocks.length,
      totalFigures: normalizedFigures.length,
      bodyStartTop: columnDetection.enabled ? roundRatio(bodyStartTop) : null,
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
        blocks: [],
      },
    };
  }

  const sortedItems = [...items].sort((left, right) => {
    if (Math.abs(left.y - right.y) > Math.max(left.height, right.height) * 0.4) {
      return right.y - left.y;
    }

    return left.x - right.x;
  });

  const lines = [];
  sortedItems.forEach((item) => {
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

  const lineBlocks = lines
    .map((line) => createLineBlock(line.items))
    .filter(Boolean)
    .sort((left, right) => {
      if (Math.abs(left.bbox.top - right.bbox.top) > 0.004) {
        return left.bbox.top - right.bbox.top;
      }

      return left.bbox.left - right.bbox.left;
    });

  const blocks = [];
  lineBlocks.forEach((lineBlock) => {
    const currentBlock = blocks[blocks.length - 1];
    if (shouldMergeLine(currentBlock, lineBlock, normalizedViewport)) {
      blocks[blocks.length - 1] = mergeLineIntoBlock(currentBlock, lineBlock);
      return;
    }

    blocks.push(lineBlock);
  });

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
    pageText: finalizedBlocks.map((block) => block.text).join('\n\n').trim(),
    pageLayout: {
      viewport: normalizedViewport,
      blocks: finalizedBlocks,
    },
  };
};

export const buildTranslationRequestPageLayout = (pageLayout, excludedZones = [], excludedZonesVersion = 1) => {
  const viewport = normalizeViewport(pageLayout?.viewport || {});
  const blocks = Array.isArray(pageLayout?.blocks)
    ? pageLayout.blocks
        .map((block) => ({
          id: String(block?.id || '').trim(),
          text: String(block?.text || '').trim(),
          bbox: normalizeRelativeBbox(block?.bbox || {}),
          style: {
            fontSize: toFiniteNumber(block?.style?.fontSize, 12),
            fontWeight: block?.style?.fontWeight === 'bold' ? 'bold' : 'normal',
            italic: Boolean(block?.style?.italic),
            textAlign: String(block?.style?.textAlign || 'left'),
          },
        }))
        .filter((block) => block.id && block.text && !isBlockInExcludedZone(block, excludedZones))
    : [];

  return {
    viewport,
    blocks,
    excludedZonesVersion: toFiniteNumber(excludedZonesVersion, 1),
  };
};
