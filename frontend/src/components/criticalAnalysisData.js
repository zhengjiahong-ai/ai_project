import { normalizeSentenceReferences, normalizeSourceLocation } from './evidenceCitationModel.js';

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

const normalizeList = (value) => {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => normalizeText(item))
    .filter(Boolean)
    .slice(0, 6);
};

const truncate = (value, maxLength = 180) => {
  const text = normalizeText(value);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}...`;
};

export const getEvidenceBasedContributions = (data) => {
  const preferred = normalizeText(data?.evidence_based_contributions);
  if (preferred) {
    return preferred;
  }
  return normalizeText(data?.inferred_real_contributions);
};

export const buildMetricCards = (data) => {
  if (Array.isArray(data?.metrics) && data.metrics.length > 0) {
    return data.metrics;
  }

  if (!data) {
    return [];
  }

  const claimedContributions = normalizeText(data.claimed_contributions);
  const evidenceBasedContributions = getEvidenceBasedContributions(data);
  const criticalAnalysis = normalizeText(data.critical_analysis);

  return [
    {
      name: '作者主张',
      score: Math.min(95, Math.max(45, Math.round(claimedContributions.length / 6) || 58)),
      detail: claimedContributions || '系统未返回作者主张摘要。',
    },
    {
      name: '真实贡献',
      score: Math.min(95, Math.max(45, Math.round(evidenceBasedContributions.length / 6) || 62)),
      detail: evidenceBasedContributions || '系统未返回推断贡献。',
    },
    {
      name: '批判深度',
      score: Math.min(95, Math.max(45, Math.round(criticalAnalysis.length / 8) || 66)),
      detail: criticalAnalysis || '系统未返回批判性结论。',
    },
  ];
};

export const buildSummary = (data) => {
  if (typeof data?.summary === 'string' && data.summary.trim()) {
    return data.summary;
  }

  const evidenceBasedContributions = getEvidenceBasedContributions(data);
  const evidenceTitle = normalizeText(data?.evidence_based_contributions)
    ? '基于证据的真实贡献'
    : '推断出的真实贡献';

  const sections = [
    ['作者宣称的贡献', normalizeText(data?.claimed_contributions)],
    [evidenceTitle, evidenceBasedContributions],
    ['批判性阅读结论', normalizeText(data?.critical_analysis)],
  ].filter(([, value]) => value);

  if (sections.length === 0) {
    return '暂无分析结果。';
  }

  return sections.map(([title, value]) => `### ${title}\n${value}`).join('\n\n');
};

export const getDetailSections = (data) => {
  const evidenceBasedContributions = getEvidenceBasedContributions(data);
  const evidenceTitle = normalizeText(data?.evidence_based_contributions)
    ? '基于证据的真实贡献'
    : '推断出的真实贡献';

  return [
    { key: 'claimed', title: '作者宣称的贡献', content: normalizeText(data?.claimed_contributions) },
    { key: 'inferred', title: evidenceTitle, content: evidenceBasedContributions },
    { key: 'critical', title: '批判性阅读结论', content: normalizeText(data?.critical_analysis) },
  ].filter((section) => section.content);
};

export const getStructuredSections = (data) =>
  [
    { key: 'weaknesses', title: '主要薄弱点', items: normalizeList(data?.weaknesses) },
    { key: 'overclaim_risks', title: '可能的夸大风险', items: normalizeList(data?.overclaim_risks) },
    { key: 'missing_evidence', title: '当前缺失证据', items: normalizeList(data?.missing_evidence) },
  ].filter((section) => section.items.length > 0);

const SOURCE_TYPE_LABELS = {
  current_paper: '当前论文',
  library: '文献库',
  unknown: '未知来源',
};

const SUPPORT_LEVEL_LABELS = {
  SUPPORTED: '已支撑',
  PARTIAL: '部分支撑',
  UNSUPPORTED: '证据不足',
};

const SUPPORT_LEVEL_STYLES = {
  SUPPORTED: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  PARTIAL: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
  UNSUPPORTED: 'border-rose-500/30 bg-rose-500/10 text-rose-600',
};

const normalizeSupportLevel = (value) => {
  const level = normalizeText(value).toUpperCase();
  return SUPPORT_LEVEL_LABELS[level] ? level : 'PARTIAL';
};

export const getEvidencePreview = (data, maxItems = 5) => {
  if (!Array.isArray(data?.rag_sources)) {
    return [];
  }

  return data.rag_sources
    .map((item, index) => {
      const sourceType = normalizeText(item?.sourceType) || 'unknown';
      const sourceId = normalizeText(item?.sourceId) || normalizeText(item?.id) || `source-${index + 1}`;
      const text = truncate(item?.text, 180);

      if (!text) {
        return null;
      }

      return {
        id: sourceId,
        sourceId,
        sourceType,
        sourceLabel: SOURCE_TYPE_LABELS[sourceType] || SOURCE_TYPE_LABELS.unknown,
        text,
        chunkIndex: normalizeInteger(item?.chunkIndex),
        ...normalizeSourceLocation(item),
      };
    })
    .filter(Boolean)
    .slice(0, maxItems);
};

export const getClaimSupportRows = (data, maxItems = 6) => {
  if (!Array.isArray(data?.claims)) {
    return [];
  }

  const sourceMap = new Map(
    (Array.isArray(data?.rag_sources) ? data.rag_sources : [])
      .map((source, index) => {
        const sourceId = normalizeText(source?.sourceId) || normalizeText(source?.id) || `source-${index + 1}`;
        if (!sourceId) {
          return null;
        }
        return [
          sourceId,
          {
            sourceId,
            preview: truncate(source?.text, 120),
            text: normalizeText(source?.text),
            sourceType: normalizeText(source?.sourceType) || 'unknown',
            chunkIndex: normalizeInteger(source?.chunkIndex),
            ...normalizeSourceLocation(source),
          },
        ];
      })
      .filter(Boolean),
  );

  return data.claims
    .map((item, index) => {
      const claim = normalizeText(item?.claim);
      if (!claim) {
        return null;
      }

      const supportLevel = normalizeSupportLevel(item?.supportLevel);
      const evidenceSourceIds = Array.isArray(item?.evidenceSourceIds)
        ? item.evidenceSourceIds.map((sourceId) => normalizeText(sourceId)).filter(Boolean)
        : [];
      const sources = evidenceSourceIds
        .map((sourceId) => sourceMap.get(sourceId))
        .filter(Boolean);

      return {
        id: normalizeText(item?.id) || `claim-${index + 1}`,
        claim,
        supportLevel,
        supportLabel: SUPPORT_LEVEL_LABELS[supportLevel],
        supportClassName: SUPPORT_LEVEL_STYLES[supportLevel],
        evidenceSourceIds,
        sources,
        missingEvidence: normalizeList(item?.missingEvidence),
        reason: normalizeText(item?.reason) || '暂无理由。',
      };
    })
    .filter(Boolean)
    .slice(0, maxItems);
};

export const getSentenceSourceReferences = (data, maxItems = 6) =>
  normalizeSentenceReferences(data?.sentenceSourceMap, data?.rag_sources, { maxItems });
