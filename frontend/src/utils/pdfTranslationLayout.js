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
    const isTrueFullWidth = spansMiddle && bbox.width >= 0.52 && Math.abs(center - 0.5) <= 0.12;
    return !isTrueFullWidth && bbox.width >= 0.12 && bbox.width <= 0.5 && bbox.top >= 0.14 && center >= 0.06 && center <= 0.94;
  });

  const leftCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 < 0.5);
  const rightCandidates = candidates.filter((item) => item.bbox.left + item.bbox.width / 2 >= 0.5);
  const leftTop = leftCandidates.length > 0 ? Math.min(...leftCandidates.map((item) => item.bbox.top)) : 1;
  const rightTop = rightCandidates.length > 0 ? Math.min(...rightCandidates.map((item) => item.bbox.top)) : 1;
  const startsInSameBodyBand = Math.abs(leftTop - rightTop) <= 0.14;
  const enabled = leftCandidates.length >= 1 && rightCandidates.length >= 1 && startsInSameBodyBand;

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
  let currentBandTop = bodyStartTop;
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
    columnDetection.enabled && bbox.top >= bodyStartTop && bbox.width <= 0.58;

  if (!canUseColumns) {
    return 'full';
  }

  if (spansMiddle && bbox.width >= 0.52 && Math.abs(center - 0.5) <= 0.12) {
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
  const viewport = pageLayout?.viewport ? normalizeViewport(pageLayout.viewport) : normalizeViewport({ width: 1, height: 1 });
  const textColumnDetection = detectColumnLayout(translatedLayoutBlocks, viewport);
  const figureColumnDetection = detectColumnLayout(normalizedFigures, viewport);
  const columnDetection = textColumnDetection.enabled ? textColumnDetection : figureColumnDetection;
  const bodyStartTop = columnDetection.bodyStartTop;

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
    viewport,
    orientation: columnDetection.orientation,
    columnMode: columnDetection.columnMode,
    mode: columnDetection.columnMode,
    sections,
    summary: {
      totalBlocks: translatedLayoutBlocks.length,
      totalFigures: normalizedFigures.length,
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
  figureSnippets = [],
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

  const figureItems = normalizeFigureSnippets(figureSnippets).map((figure, index) => {
    const lane = resolveLayoutLane(figure.bbox);
    return {
      ...figure,
      kind: 'figure',
      readingOrder: Number.MAX_SAFE_INTEGER / 4 + index,
      lane,
      frame: applyColumnFrame(toPageWidthUnits(figure.bbox, pageAspectRatio), lane, columnLayout),
    };
  });

  const sourceItems = sortPositionedItems([...textItems, ...figureItems]);
  if (sourceItems.length === 0) {
    return null;
  }

  const positionedItems = sourceItems.reduce((accumulator, item) => {
    const baseHeight = Math.max(toFiniteNumber(item?.frame?.height, 0), 0.018);
    const resolvedHeight =
      item.kind === 'text'
        ? Math.max(baseHeight, toFiniteNumber(normalizedMeasuredHeights[item.id], 0))
        : baseHeight;

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
      totalFigures: figureItems.length,
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
    .flatMap((line) => splitLineItemsIntoSegments(line.items, normalizedViewport))
    .map((segmentItems) => createLineBlock(segmentItems))
    .filter(Boolean);

  const lineColumnLayout = detectColumnLayout(lineBlocks, normalizedViewport);
  const orderedLineBlocks = buildColumnFirstReadingOrder(lineBlocks, normalizedViewport);
  const shouldPreserveLineBoxes =
    lineColumnLayout.orientation === 'portrait' && lineColumnLayout.columnMode === 'two-column';

  const blocks = shouldPreserveLineBoxes ? orderedLineBlocks : [];
  if (!shouldPreserveLineBoxes) {
    orderedLineBlocks.forEach((lineBlock) => {
      const currentBlock = blocks[blocks.length - 1];
      if (
        canMergeInColumnLayout(currentBlock, lineBlock, lineColumnLayout) &&
        shouldMergeLine(currentBlock, lineBlock, normalizedViewport)
      ) {
        blocks[blocks.length - 1] = mergeLineIntoBlock(currentBlock, lineBlock);
        return;
      }

      blocks.push(lineBlock);
    });
  }

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
