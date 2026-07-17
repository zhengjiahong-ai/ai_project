import { normalizeSentenceReferences, normalizeSourceLocation } from './evidenceCitationModel.ts';

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

const normalizeScore = (value: unknown, fallback: number | null = 0): number | null => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(100, Math.max(0, Math.round(parsed)));
};

const normalizeList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item: unknown) => normalizeText(item))
    .filter(Boolean)
    .slice(0, 6);
};

const truncate = (value: unknown, maxLength = 180): string => {
  const text = normalizeText(value);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}...`;
};

interface ScoreCardInput {
  score?: unknown;
  label?: unknown;
  level?: unknown;
  summary?: unknown;
  factors?: unknown;
}

const normalizeScoreCard = (value: unknown): { score: number; label: string; level: string; summary: string; basis: string[] } | null => {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const obj = value as ScoreCardInput;

  const score = normalizeScore(obj.score, null);
  if (score === null) {
    return null;
  }

  return {
    score,
    label: normalizeText(obj.label),
    level: normalizeText(obj.level),
    summary: normalizeText(obj.summary),
    basis: normalizeList(obj.factors),
  };
};

const DIMENSION_STATUS_LABELS: Record<string, string> = {
  strong: '强',
  partial: '中',
  weak: '弱',
};

interface NoveltyDimensionInput {
  id?: unknown;
  label?: unknown;
  status?: unknown;
  score?: unknown;
  detail?: unknown;
}

export const getNoveltyDimensionRows = (data: Record<string, unknown> | null | undefined, maxItems = 4) => {
  if (!Array.isArray(data?.noveltyDimensions)) {
    return [];
  }

  return (data.noveltyDimensions as NoveltyDimensionInput[])
    .map((item) => {
      const id = normalizeText(item?.id);
      const label = normalizeText(item?.label);
      if (!id || !label) {
        return null;
      }
      const status = normalizeText(item?.status) || 'partial';
      const score = normalizeScore(item?.score, 0);
      return {
        id,
        label,
        score,
        status,
        statusLabel: DIMENSION_STATUS_LABELS[status] || '中',
        detail: normalizeText(item?.detail) || '暂无评分依据。',
      };
    })
    .filter((item): item is NonNullable<typeof item> => item != null)
    .slice(0, maxItems);
};

interface CitationNode {
  id?: unknown;
  name?: unknown;
  label?: unknown;
  [key: string]: unknown;
}

interface CitationLink {
  source?: unknown;
  target?: unknown;
  [key: string]: unknown;
}

export const getCitationGraph = (data: Record<string, unknown> | null | undefined) => {
  const graph = data?.citationGraph as Record<string, unknown> | undefined;
  if (!graph || typeof graph !== 'object') {
    return null;
  }

  const nodes = Array.isArray(graph.nodes)
    ? (graph.nodes as CitationNode[])
      .map((node) => {
        const id = normalizeText(node?.id);
        if (!id) {
          return null;
        }
        return {
          ...node,
          id,
          name: normalizeText(node?.name) || normalizeText(node?.label) || id,
        };
      })
      .filter((item): item is NonNullable<typeof item> => item != null)
    : [];

  const links = Array.isArray(graph.links)
    ? (graph.links as CitationLink[])
      .map((link) => {
        const source = normalizeText(link?.source);
        const target = normalizeText(link?.target);
        if (!source || !target) {
          return null;
        }
        return {
          ...link,
          source,
          target,
        };
      })
      .filter((item): item is NonNullable<typeof item> => item != null)
    : [];

  if (nodes.length === 0 || links.length === 0) {
    return null;
  }

  return { nodes, links };
};

export const getEvidenceBasedContributions = (data: Record<string, unknown> | null | undefined): string => {
  const preferred = normalizeText(data?.evidence_based_contributions);
  if (preferred) {
    return preferred;
  }
  return normalizeText(data?.inferred_real_contributions);
};

export const buildMetricCards = (data: Record<string, unknown> | null | undefined): Record<string, unknown>[] => {
  if (Array.isArray(data?.metrics) && data.metrics.length > 0) {
    return data.metrics as Record<string, unknown>[];
  }

  if (!data) {
    return [];
  }

  const contributionScore = normalizeScoreCard((data as Record<string, unknown>).contributionScore);
  const riskScore = normalizeScoreCard((data as Record<string, unknown>).riskScore);
  const noveltyDimensions = getNoveltyDimensionRows(data);

  if (contributionScore || riskScore || noveltyDimensions.length > 0) {
    const coverageScore = noveltyDimensions.length > 0
      ? normalizeScore(
        noveltyDimensions.reduce((sum: number, item) => sum + (item.score ?? 0), 0) / noveltyDimensions.length,
        0,
      )
      : 0;

    return [
      {
        name: '核心贡献可信度',
        score: contributionScore?.score ?? coverageScore,
        detail: contributionScore?.summary || '系统暂未返回核心贡献可信度摘要。',
        label: contributionScore?.label || '',
        basis: contributionScore?.basis || [],
      },
      {
        name: '伪贡献/夸大风险',
        score: riskScore?.score ?? 0,
        detail: riskScore?.summary || '系统暂未返回风险评分摘要。',
        label: riskScore?.label || '',
        basis: riskScore?.basis || [],
      },
      {
        name: '证据验证覆盖',
        score: coverageScore,
        detail: noveltyDimensions.length > 0
          ? noveltyDimensions.map((item) => `${item.label}: ${item.score} 分`).join('；')
          : '系统暂未返回分维度证据覆盖评分。',
        label: '',
        basis: noveltyDimensions.map((item) => `${item.label} ${item.statusLabel}: ${item.detail}`),
      },
    ];
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

export const buildSummary = (data: Record<string, unknown> | null | undefined): string => {
  if (typeof data?.summary === 'string' && data.summary.trim()) {
    return data.summary;
  }

  const evidenceBasedContributions = getEvidenceBasedContributions(data);
  const evidenceTitle = normalizeText(data?.evidence_based_contributions)
    ? '基于证据的真实贡献'
    : '推断出的真实贡献';

  const sections: [string, string][] = ([
    ['作者宣称的贡献', normalizeText(data?.claimed_contributions)],
    [evidenceTitle, evidenceBasedContributions],
    ['批判性阅读结论', normalizeText(data?.critical_analysis)],
  ] as [string, string][]).filter(([, value]) => value);

  if (sections.length === 0) {
    return '暂无分析结果。';
  }

  return sections.map(([title, value]) => `### ${title}\n${value}`).join('\n\n');
};

export const getDetailSections = (data: Record<string, unknown> | null | undefined) => {
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

export const getStructuredSections = (data: Record<string, unknown> | null | undefined) =>
  [
    { key: 'weaknesses', title: '主要薄弱点', items: normalizeList(data?.weaknesses) },
    { key: 'overclaim_risks', title: '可能的夸大风险', items: normalizeList(data?.overclaim_risks) },
    { key: 'missing_evidence', title: '当前缺失证据', items: normalizeList(data?.missing_evidence) },
  ].filter((section) => section.items.length > 0);

const SOURCE_TYPE_LABELS: Record<string, string> = {
  current_paper: '当前论文',
  library: '文献库',
  unknown: '未知来源',
};

const SUPPORT_LEVEL_LABELS: Record<string, string> = {
  SUPPORTED: '已支撑',
  PARTIAL: '部分支撑',
  UNSUPPORTED: '证据不足',
};

const SUPPORT_LEVEL_STYLES: Record<string, string> = {
  SUPPORTED: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600',
  PARTIAL: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
  UNSUPPORTED: 'border-rose-500/30 bg-rose-500/10 text-rose-600',
};

const NUMERIC_VERIFICATION_LABELS: Record<string, string> = {
  not_applicable: '不涉及数值核对',
  candidate_found: '找到候选数值证据',
  insufficient_for_auto_verification: '候选证据不足以自动验证',
  not_found: '未找到对应数值证据',
};

const normalizeSupportLevel = (value: unknown): string => {
  const level = normalizeText(value).toUpperCase();
  return SUPPORT_LEVEL_LABELS[level] ? level : 'PARTIAL';
};

const normalizeNumericVerificationStatus = (value: unknown): string => {
  const status = normalizeText(value);
  return NUMERIC_VERIFICATION_LABELS[status] ? status : 'not_applicable';
};

export const getEvidencePreview = (data: Record<string, unknown> | null | undefined, maxItems = 5) => {
  if (!Array.isArray(data?.rag_sources)) {
    return [];
  }

  return (data.rag_sources as Record<string, unknown>[])
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
        ...normalizeSourceLocation(item as Record<string, unknown>),
      };
    })
    .filter((item): item is NonNullable<typeof item> => item != null)
    .slice(0, maxItems);
};

export const getClaimSupportRows = (data: Record<string, unknown> | null | undefined, maxItems = 6) => {
  if (!Array.isArray(data?.claims)) {
    return [];
  }

  const sourceMap = new Map(
    (Array.isArray(data?.rag_sources) ? data.rag_sources as Record<string, unknown>[] : [])
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
        ] as const;
      })
      .filter((item): item is NonNullable<typeof item> => item != null),
  );

  return (data.claims as Record<string, unknown>[])
    .map((item, index) => {
      const claim = normalizeText(item?.claim);
      if (!claim) {
        return null;
      }

      const supportLevel = normalizeSupportLevel(item?.supportLevel);
      const evidenceSourceIds = Array.isArray(item?.evidenceSourceIds)
        ? (item.evidenceSourceIds as unknown[]).map((sourceId: unknown) => normalizeText(sourceId)).filter(Boolean)
        : [];
      const sources = evidenceSourceIds
        .map((sourceId: string) => sourceMap.get(sourceId))
        .filter(Boolean);
      const numericVerificationStatus = normalizeNumericVerificationStatus(item?.numericVerificationStatus);
      const numericEvidenceCandidates = Array.isArray(item?.numericEvidenceCandidates)
        ? (item.numericEvidenceCandidates as Record<string, unknown>[])
          .map((candidate, candidateIndex) => {
            const sourceId = normalizeText(candidate?.sourceId) || normalizeText(candidate?.id);
            if (!sourceId) {
              return null;
            }
            const source = sourceMap.get(sourceId) as Record<string, unknown> | undefined;
            const text = normalizeText(candidate?.text) || (source?.text as string) || '';
            if (!text) {
              return null;
            }
            return {
              id: normalizeText(candidate?.id) || `${sourceId}-numeric-${candidateIndex + 1}`,
              sourceId,
              text,
              preview: truncate(text, 140),
              label: normalizeText(candidate?.label),
              metrics: normalizeList(candidate?.metrics),
              numbers: normalizeList(candidate?.numbers),
              reason: normalizeText(candidate?.reason),
              status: normalizeText(candidate?.status) || 'candidate_found',
              chunkIndex: normalizeInteger(candidate?.chunkIndex) ?? (source?.chunkIndex as number | null) ?? null,
              ...normalizeSourceLocation({
                ...(source || {}),
                ...candidate,
              } as Record<string, unknown>),
            };
          })
          .filter((item): item is NonNullable<typeof item> => item != null)
          .slice(0, 3)
        : [];

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
        numericVerificationStatus,
        numericVerificationStatusLabel: NUMERIC_VERIFICATION_LABELS[numericVerificationStatus],
        numericEvidenceCandidates,
      };
    })
    .filter((item): item is NonNullable<typeof item> => item != null)
    .slice(0, maxItems);
};

export const getSentenceSourceReferences = (data: Record<string, unknown> | null | undefined, maxItems = 6) =>
  normalizeSentenceReferences(data?.sentenceSourceMap as unknown[], data?.rag_sources as unknown[], { maxItems });
