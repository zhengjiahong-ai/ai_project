const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const truncate = (value, maxLength = 180) => {
  const text = normalizeText(value);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}...`;
};

export const buildSourceLookup = (sources) => {
  if (!Array.isArray(sources)) {
    return new Map();
  }

  const lookup = new Map();
  sources.forEach((source, index) => {
    const sourceId = normalizeText(source?.sourceId) || normalizeText(source?.id) || `source-${index + 1}`;
    const text = normalizeText(source?.text);
    if (!sourceId || !text) {
      return;
    }
    lookup.set(sourceId, {
      sourceId,
      text,
      preview: truncate(text),
      sourceType: normalizeText(source?.sourceType) || 'unknown',
      chunkIndex: Number.isInteger(source?.chunkIndex) ? source.chunkIndex : null,
    });
  });
  return lookup;
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
