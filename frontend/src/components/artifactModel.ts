const normalizeText = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

const normalizeStringList = (value: unknown): string[] =>
  (Array.isArray(value) ? value : [])
    .map((item: unknown) => normalizeText(item))
    .filter(Boolean);

const normalizeId = (value: unknown): string | null => normalizeText(value) || null;

const summarize = (value: unknown, fallback: string): string => {
  const text = normalizeText(value).replace(/\s+/g, ' ');
  if (!text) return fallback;
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
};

const escapeMarkdownCell = (value: unknown): string => normalizeText(`${value ?? ''}`).replace(/\|/g, '\\|') || '-';

interface ComparisonTableInput {
  columns?: unknown[];
  rows?: unknown[];
}

export const serializeComparisonTable = (comparisonTable: ComparisonTableInput = {}): string => {
  const columns: string[] = Array.isArray(comparisonTable?.columns) ? comparisonTable.columns.map(escapeMarkdownCell) : [];
  const rawRows: unknown[] = Array.isArray(comparisonTable?.rows) ? comparisonTable.rows : [];
  const rows: unknown[][] = rawRows as unknown[][];
  if (columns.length === 0 || rows.length === 0) return '';

  const normalizeRow = (row: unknown): string =>
    columns.map((_, index) => escapeMarkdownCell(Array.isArray(row) ? row[index] : '')).join(' | ');
  return [
    `| ${columns.join(' | ')} |`,
    `| ${columns.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${normalizeRow(row)} |`),
  ].join('\n');
};

interface InsightArtifactInput {
  artifactId?: string | null;
  kind?: string;
  title?: string;
  summary?: string;
  content?: string;
  sourceSelectionId?: string | null;
  sourceMessageId?: string | null;
  pdfId?: string | null;
  sourceId?: string | null;
  taskId?: string | null;
  projectId?: string | null;
  pageIndex?: number | null;
  sectionId?: string;
  tags?: string[];
  displayMode?: string;
  position?: string;
  lane?: string;
  pinned?: boolean;
  userNote?: string;
  sourceAnchorId?: string | null;
  sourceActionId?: string | null;
  sourceActionLabel?: string;
  createdAt?: number | null;
  updatedAt?: number | null;
  id?: string;
  isPinned?: boolean;
}

export const createInsightArtifact = ({
  artifactId,
  kind = 'insight',
  title = '',
  summary = '',
  content = '',
  sourceSelectionId = null,
  sourceMessageId = null,
  pdfId = null,
  sourceId = null,
  taskId = null,
  projectId = null,
  pageIndex = null,
  sectionId = '',
  tags = [],
  displayMode = 'card',
  position = 'workbench',
  lane = 'inbox',
  pinned = false,
  userNote = '',
  sourceAnchorId = null,
  sourceActionId = null,
  sourceActionLabel = '',
  createdAt = null,
  updatedAt = null,
}: InsightArtifactInput = {}) => ({
  artifactId: artifactId || `artifact-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  kind: normalizeText(kind) || 'insight',
  title: normalizeText(title) || '未命名卡片',
  summary: normalizeText(summary) || '暂无摘要。',
  content: normalizeText(content),
  sourceSelectionId: normalizeText(sourceSelectionId) || null,
  sourceMessageId: normalizeText(sourceMessageId) || null,
  pdfId: normalizeId(pdfId),
  sourceId: normalizeId(sourceId),
  taskId: normalizeId(taskId),
  projectId: normalizeId(projectId),
  pageIndex: Number.isFinite(pageIndex) ? pageIndex : null,
  sectionId: normalizeText(sectionId),
  tags: normalizeStringList(tags),
  displayMode: normalizeText(displayMode) || 'card',
  position: normalizeText(position) || 'workbench',
  lane: normalizeText(lane) || 'inbox',
  pinned: Boolean(pinned),
  userNote: normalizeText(userNote),
  sourceAnchorId: normalizeText(sourceAnchorId) || null,
  sourceActionId: normalizeText(sourceActionId) || null,
  sourceActionLabel: normalizeText(sourceActionLabel),
  createdAt: Number.isFinite(createdAt) ? createdAt : Date.now(),
  updatedAt: Number.isFinite(updatedAt) ? updatedAt : Date.now(),
});

interface TranslationArtifactInput {
  pdfId?: string | null;
  pdfFileName?: string;
  pageIndex?: number | null;
  translatedText?: string;
}

export const buildTranslationArtifact = ({ pdfId, pdfFileName = '', pageIndex = null, translatedText = '' }: TranslationArtifactInput = {}) => {
  const content = normalizeText(translatedText);
  const normalizedPdfId = normalizeId(pdfId);
  if (!normalizedPdfId || !content) return null;

  const pageNumber = Number.isFinite(pageIndex) ? (pageIndex as number) + 1 : 1;
  const fileLabel = normalizeText(pdfFileName);
  return createInsightArtifact({
    kind: 'translation-page',
    title: `${fileLabel ? `${fileLabel} · ` : ''}第 ${pageNumber} 页译文`,
    summary: summarize(content, '当前页译文'),
    content,
    pdfId: normalizedPdfId,
    pageIndex,
    tags: ['translation', 'page'],
  });
};

interface DeconstructionArtifactInput {
  pdfId?: string | null;
  sectionId?: string;
  sectionLabel?: string;
  content?: string;
}

export const buildDeconstructionArtifact = ({ pdfId, sectionId = '', sectionLabel = '', content = '' }: DeconstructionArtifactInput = {}) => {
  const normalizedContent = normalizeText(content);
  const normalizedPdfId = normalizeId(pdfId);
  const normalizedSectionId = normalizeText(sectionId);
  if (!normalizedPdfId || !normalizedContent || !normalizedSectionId) return null;

  const label = normalizeText(sectionLabel) || normalizedSectionId;
  return createInsightArtifact({
    kind: 'paper-section',
    title: `篇章解构 · ${label}`,
    summary: summarize(normalizedContent, `${label}章节摘要`),
    content: normalizedContent,
    pdfId: normalizedPdfId,
    sectionId: normalizedSectionId,
    tags: ['deconstruction', 'section', normalizedSectionId],
  });
};

interface AgentReportArtifactInput {
  activePdfId?: string | null;
  projectId?: string | null;
  taskId?: string | null;
  projectTitle?: string;
  draftReport?: string;
}

export const buildAgentReportArtifact = ({
  activePdfId,
  projectId,
  taskId,
  projectTitle = '',
  draftReport = '',
}: AgentReportArtifactInput = {}) => {
  const content = normalizeText(draftReport);
  const pdfId = normalizeId(activePdfId);
  if (!pdfId || !content) return null;

  const title = normalizeText(projectTitle) || 'Agent 研究';
  return createInsightArtifact({
    kind: 'agent-report',
    title: `${title} · 报告草稿`,
    summary: summarize(content, 'Agent 报告草稿'),
    content,
    pdfId,
    projectId,
    taskId,
    tags: ['agent', 'report'],
  });
};

interface AgentComparisonArtifactInput {
  activePdfId?: string | null;
  projectId?: string | null;
  taskId?: string | null;
  projectTitle?: string;
  comparisonTable?: ComparisonTableInput;
}

export const buildAgentComparisonArtifact = ({
  activePdfId,
  projectId,
  taskId,
  projectTitle = '',
  comparisonTable,
}: AgentComparisonArtifactInput = {}) => {
  const content = serializeComparisonTable(comparisonTable);
  const pdfId = normalizeId(activePdfId);
  if (!pdfId || !content) return null;

  const title = normalizeText(projectTitle) || 'Agent 研究';
  const rowCount = comparisonTable?.rows?.length ?? 0;
  return createInsightArtifact({
    kind: 'agent-comparison',
    title: `${title} · 跨论文对比`,
    summary: `已整理 ${rowCount} 条跨论文比较结果。`,
    content,
    pdfId,
    projectId,
    taskId,
    tags: ['agent', 'comparison'],
  });
};

interface AgentEvidenceInput {
  text?: string;
  sourceId?: string | null;
  pdfId?: string | null;
  pageIndex?: number | null;
  sectionId?: string;
  sourceType?: string;
}

interface AgentEvidenceArtifactInput {
  activePdfId?: string | null;
  projectId?: string | null;
  taskId?: string | null;
  evidence?: AgentEvidenceInput;
}

export const buildAgentEvidenceArtifact = ({ activePdfId, projectId, taskId, evidence }: AgentEvidenceArtifactInput = {}) => {
  const content = normalizeText(evidence?.text);
  if (!normalizeId(activePdfId) || !content) return null;

  const sourceId = normalizeId(evidence?.sourceId);
  const sourceLabel = normalizeText(evidence?.pdfId || sourceId) || '关键证据';
  return createInsightArtifact({
    kind: 'agent-evidence',
    title: `Agent 证据 · ${sourceLabel}`,
    summary: summarize(content, 'Agent 关键证据'),
    content,
    pdfId: normalizeId(evidence?.pdfId) || normalizeId(activePdfId),
    sourceId,
    taskId,
    projectId,
    pageIndex: evidence?.pageIndex ?? null,
    sectionId: evidence?.sectionId ?? '',
    tags: ['agent', 'evidence', evidence?.sourceType ?? ''],
  });
};

export const normalizeInsightArtifact = (artifact: InsightArtifactInput | null | undefined): ReturnType<typeof createInsightArtifact> | null => {
  if (!artifact || typeof artifact !== 'object') {
    return null;
  }

  return createInsightArtifact({
    ...artifact,
    artifactId: normalizeText(artifact.artifactId || artifact.id),
    pinned: artifact.pinned ?? artifact.isPinned,
  });
};

export const normalizeInsightArtifacts = (artifacts: unknown[] = []): ReturnType<typeof createInsightArtifact>[] =>
  (Array.isArray(artifacts) ? artifacts : [])
    .map((artifact: unknown) => normalizeInsightArtifact(artifact as InsightArtifactInput))
    .filter((item): item is NonNullable<ReturnType<typeof createInsightArtifact>> => item != null)
    .sort((left, right) => Number(right.pinned) - Number(left.pinned) || (right.createdAt as number) - (left.createdAt as number));

export const updateInsightArtifact = (artifact: InsightArtifactInput | null | undefined, patch: Partial<InsightArtifactInput> = {}): ReturnType<typeof createInsightArtifact> | null => {
  if (!artifact) {
    return null;
  }

  return createInsightArtifact({
    ...artifact,
    ...patch,
    artifactId: artifact.artifactId,
    createdAt: artifact.createdAt,
    updatedAt: Date.now(),
  });
};
