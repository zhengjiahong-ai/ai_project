const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const normalizeInteger = (value) => {
  if (Number.isInteger(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }
  return null;
};

const truncate = (value, maxLength = 180) => {
  const text = normalizeText(value);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}...`;
};

export const normalizeSourceLocation = (source) => {
  const metadata = source?.metadata && typeof source.metadata === 'object' ? source.metadata : {};
  const pageIndex = normalizeInteger(source?.pageIndex ?? source?.sourcePageIndex ?? metadata.pageIndex);
  const sectionId = normalizeText(source?.sectionId ?? metadata.sectionId);
  return {
    pageIndex,
    sectionId: sectionId || null,
    pdfId: normalizeText(source?.pdfId ?? metadata.pdfId) || null,
    canJumpToSource: Number.isInteger(pageIndex),
    locationLabel: Number.isInteger(pageIndex) ? `p.${pageIndex + 1}` : '',
  };
};

export const normalizeEvidenceSource = (source, index = 0) => {
  if (!source || typeof source !== 'object') {
    return null;
  }

  const metadata = source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
  const sourceId = normalizeText(source.sourceId) || normalizeText(source.id) || `source-${index + 1}`;
  const text = normalizeText(source.text) || normalizeText(source.content) || normalizeText(source.preview);
  const location = normalizeSourceLocation(source);
  if (!text && !Number.isInteger(location.pageIndex) && !location.sectionId) {
    return null;
  }

  return {
    sourceId,
    sourceType: normalizeText(source.sourceType ?? metadata.sourceType) || 'unknown',
    text,
    preview: truncate(text),
    chunkIndex: normalizeInteger(source.chunkIndex ?? metadata.chunkIndex),
    ...location,
  };
};

export const normalizeEvidenceSources = (sources) => {
  if (!Array.isArray(sources)) {
    return [];
  }

  const seen = new Set();
  return sources
    .map(normalizeEvidenceSource)
    .filter((source) => {
      if (!source || seen.has(source.sourceId)) {
        return false;
      }
      seen.add(source.sourceId);
      return true;
    });
};

export const buildSourceLookup = (sources) => {
  if (!Array.isArray(sources)) {
    return new Map();
  }

  const lookup = new Map();
  normalizeEvidenceSources(sources).forEach((source) => lookup.set(source.sourceId, source));
  return lookup;
};

export const collectSourcesByIds = (sourceIds, sources) => {
  if (!Array.isArray(sourceIds)) {
    return [];
  }

  const lookup = buildSourceLookup(sources);
  const seen = new Set();
  return sourceIds
    .map((sourceId) => normalizeText(sourceId))
    .filter((sourceId) => sourceId && !seen.has(sourceId) && seen.add(sourceId))
    .map((sourceId) => lookup.get(sourceId))
    .filter(Boolean);
};

export const normalizeSentenceReferences = (sentenceSourceMap, sources, options = {}) => {
  if (!Array.isArray(sentenceSourceMap)) {
    return [];
  }

  const sourceLookup = buildSourceLookup(sources);
  const targetFilter = normalizeText(options.target);
  const maxItems = Number.isInteger(options.maxItems) ? options.maxItems : 8;

  return sentenceSourceMap
    .map((item, index) => {
      const target = normalizeText(item?.target) || 'message';
      if (targetFilter && target !== targetFilter) {
        return null;
      }

      const sentence = truncate(item?.sentence, 220);
      if (!sentence) {
        return null;
      }

      const sourceIds = Array.isArray(item?.sourceIds) ? item.sourceIds : [];
      const sourcesForReference = sourceIds
        .map((sourceId) => sourceLookup.get(normalizeText(sourceId)))
        .filter(Boolean);

      if (sourcesForReference.length === 0) {
        return null;
      }

      return {
        id: normalizeText(item?.id) || `ref-${index + 1}`,
        target,
        sentence,
        confidence: Number.isFinite(Number(item?.confidence)) ? Number(item.confidence) : null,
        sources: sourcesForReference,
        sourceIds: sourcesForReference.map((source) => source.sourceId),
      };
    })
    .filter(Boolean)
    .slice(0, maxItems);
};
