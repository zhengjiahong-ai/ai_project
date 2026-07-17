const normalizeText = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

const normalizeInteger = (value: unknown): number | null => {
  if (Number.isInteger(value)) {
    return value as number;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }
  return null;
};

const truncate = (value: unknown, maxLength = 180): string => {
  const text = normalizeText(value);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}...`;
};

const EXTERNAL_SOURCE_TYPE = 'external_academic';

const isExternalSource = (source: Record<string, any>): boolean => {
  const sourceType = normalizeText(source?.sourceType ?? source?.metadata?.sourceType);
  if (sourceType === EXTERNAL_SOURCE_TYPE) {
    return true;
  }
  return Boolean(normalizeText(source?.provider) || normalizeText(source?.doi));
};

export const normalizeSourceLocation = (source: Record<string, any>) => {
  const metadata = source?.metadata && typeof source.metadata === 'object' ? source.metadata : {};
  const pageIndex = normalizeInteger(source?.pageIndex ?? source?.sourcePageIndex ?? metadata.pageIndex);
  const sectionId = normalizeText(source?.sectionId ?? metadata.sectionId);
  return {
    pageIndex,
    sectionId: sectionId || null,
    pdfId: normalizeText(source?.pdfId ?? metadata.pdfId) || null,
    canJumpToSource: Number.isInteger(pageIndex),
    locationLabel: Number.isInteger(pageIndex) ? `p.${(pageIndex as number) + 1}` : '',
  };
};

const normalizeExternalSourceLocation = (source: Record<string, any>) => {
  const provider = normalizeText(source?.provider ?? source?.metadata?.provider);
  const year = normalizeInteger(source?.year ?? source?.metadata?.year);
  const doi = normalizeText(source?.doi ?? source?.metadata?.doi);
  const url = normalizeText(source?.url ?? source?.metadata?.url);
  const hasUrl = Boolean(url);
  const hasDoi = Boolean(doi);
  const hasLink = hasUrl || hasDoi;
  return {
    provider: provider || 'unknown',
    year,
    doi: doi || '',
    url: url || '',
    canJumpToSource: hasLink,
    locationLabel: [provider, year ? String(year) : ''].filter(Boolean).join(' · ') || '外部来源',
    externalUrl: hasUrl ? url : (hasDoi ? `https://doi.org/${doi}` : ''),
  };
};

export const normalizeEvidenceSource = (source: Record<string, any>, index = 0) => {
  if (!source || typeof source !== 'object') {
    return null;
  }

  const metadata = source.metadata && typeof source.metadata === 'object' ? source.metadata : {};
  const sourceId = normalizeText(source.sourceId) || normalizeText(source.id) || `source-${index + 1}`;
  const sourceType = normalizeText(source.sourceType ?? metadata.sourceType) || 'unknown';
  const text = normalizeText(source.text) || normalizeText(source.content) || normalizeText(source.preview);
  const external = isExternalSource(source);

  if (external) {
    const extLocation = normalizeExternalSourceLocation(source);
    const title = normalizeText(source?.title ?? metadata?.title);
    const abstract = normalizeText(source?.abstract ?? metadata?.abstract);
    const authors = Array.isArray(source?.authors ?? metadata?.authors)
      ? (source?.authors ?? metadata?.authors).map((author: unknown) => normalizeText(author)).filter(Boolean)
      : [];
    const retrievedAt = normalizeText(source?.retrievedAt ?? metadata?.retrievedAt);
    const license = normalizeText(source?.license ?? metadata?.license);

    if (!text && !title && !extLocation.doi && !extLocation.url && authors.length === 0) {
      return null;
    }

    const provenance = source?.provenance && typeof source.provenance === 'object'
      ? {
          discoveryPath: normalizeText(source.provenance.discoveryPath),
          searchQuery: normalizeText(source.provenance.searchQuery),
          searchIteration: Number.isInteger(source.provenance.searchIteration)
            ? source.provenance.searchIteration
            : null,
          sourceUrl: normalizeText(source.provenance.sourceUrl),
          retrievalTimestamp: normalizeText(source.provenance.retrievalTimestamp),
        }
      : null;

    return {
      sourceId,
      sourceType: EXTERNAL_SOURCE_TYPE,
      text,
      preview: truncate(text || title),
      chunkIndex: null,
      pageIndex: null,
      sectionId: null,
      pdfId: null,
      isExternal: true,
      provider: extLocation.provider,
      providerId: normalizeText(source?.providerId ?? metadata?.providerId),
      title,
      authors,
      year: extLocation.year,
      doi: extLocation.doi,
      url: extLocation.url,
      externalUrl: extLocation.externalUrl,
      retrievedAt,
      license,
      abstract,
      provenance,
      canJumpToSource: extLocation.canJumpToSource,
      locationLabel: extLocation.locationLabel,
    };
  }

  const location = normalizeSourceLocation(source);
  if (!text && !Number.isInteger(location.pageIndex) && !location.sectionId) {
    return null;
  }

  return {
    sourceId,
    sourceType,
    text,
    preview: truncate(text),
    chunkIndex: normalizeInteger(source.chunkIndex ?? metadata.chunkIndex),
    isExternal: false,
    ...location,
  };
};

export const normalizeEvidenceSources = (sources: unknown): unknown[] => {
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

export const buildSourceLookup = (sources: unknown) => {
  if (!Array.isArray(sources)) {
    return new Map();
  }

  const lookup = new Map();
  normalizeEvidenceSources(sources).forEach((source) => { if (source) lookup.set((source as Record<string, any>).sourceId as string, source); });
  return lookup;
};

export const collectSourcesByIds = (sourceIds: unknown, sources: unknown) => {
  if (!Array.isArray(sourceIds)) {
    return [];
  }

  const lookup = buildSourceLookup(sources);
  const seen = new Set();
  return sourceIds
    .map((sourceId: unknown) => normalizeText(sourceId))
    .filter((sourceId) => sourceId && !seen.has(sourceId) && seen.add(sourceId))
    .map((sourceId: unknown) => lookup.get(sourceId))
    .filter(Boolean);
};

export const normalizeSentenceReferences = (sentenceSourceMap: unknown, sources: unknown, options: Record<string, any> = {}) => {
  if (!Array.isArray(sentenceSourceMap)) {
    return [];
  }

  const sourceLookup = buildSourceLookup(sources);
  const opts = options as Record<string, any>;
  const targetFilter = normalizeText(opts.target);
  const maxItems = Number.isInteger(opts.maxItems) ? (opts.maxItems as number) : 8;

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
        .map((sourceId: unknown) => sourceLookup.get(normalizeText(sourceId)))
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
        sourceIds: sourcesForReference.map((source: Record<string, any>) => source.sourceId),
      };
    })
    .filter(Boolean)
    .slice(0, maxItems);
};
