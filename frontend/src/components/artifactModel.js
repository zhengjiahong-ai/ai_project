const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const normalizeStringList = (value) =>
  (Array.isArray(value) ? value : [])
    .map((item) => normalizeText(item))
    .filter(Boolean);

const normalizeId = (value) => normalizeText(value) || null;

const summarize = (value, fallback) => {
  const text = normalizeText(value).replace(/\s+/g, ' ');
  if (!text) return fallback;
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
};

const escapeMarkdownCell = (value) => normalizeText(`${value ?? ''}`).replace(/\|/g, '\\|') || '-';

export const serializeComparisonTable = (comparisonTable = {}) => {
  const columns = Array.isArray(comparisonTable?.columns) ? comparisonTable.columns.map(escapeMarkdownCell) : [];
  const rows = Array.isArray(comparisonTable?.rows) ? comparisonTable.rows : [];
  if (columns.length === 0 || rows.length === 0) return '';

  const normalizeRow = (row) =>
    columns.map((_, index) => escapeMarkdownCell(Array.isArray(row) ? row[index] : '')).join(' | ');
  return [
    `| ${columns.join(' | ')} |`,
    `| ${columns.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${normalizeRow(row)} |`),
  ].join('\n');
};

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
} = {}) => ({
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

export const buildTranslationArtifact = ({ pdfId, pdfFileName = '', pageIndex = null, translatedText = '' } = {}) => {
  const content = normalizeText(translatedText);
  const normalizedPdfId = normalizeId(pdfId);
  if (!normalizedPdfId || !content) return null;

  const pageNumber = Number.isFinite(pageIndex) ? pageIndex + 1 : 1;
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

export const buildDeconstructionArtifact = ({ pdfId, sectionId = '', sectionLabel = '', content = '' } = {}) => {
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

export const buildAgentReportArtifact = ({
  activePdfId,
  projectId,
  taskId,
  projectTitle = '',
  draftReport = '',
} = {}) => {
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

export const buildAgentComparisonArtifact = ({
  activePdfId,
  projectId,
  taskId,
  projectTitle = '',
  comparisonTable,
} = {}) => {
  const content = serializeComparisonTable(comparisonTable);
  const pdfId = normalizeId(activePdfId);
  if (!pdfId || !content) return null;

  const title = normalizeText(projectTitle) || 'Agent 研究';
  return createInsightArtifact({
    kind: 'agent-comparison',
    title: `${title} · 跨论文对比`,
    summary: `已整理 ${comparisonTable.rows.length} 条跨论文比较结果。`,
    content,
    pdfId,
    projectId,
    taskId,
    tags: ['agent', 'comparison'],
  });
};

export const buildAgentEvidenceArtifact = ({ activePdfId, projectId, taskId, evidence } = {}) => {
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
    pageIndex: evidence?.pageIndex,
    sectionId: evidence?.sectionId,
    tags: ['agent', 'evidence', evidence?.sourceType],
  });
};

export const normalizeInsightArtifact = (artifact) => {
  if (!artifact || typeof artifact !== 'object') {
    return null;
  }

  return createInsightArtifact({
    ...artifact,
    artifactId: normalizeText(artifact.artifactId || artifact.id),
    pinned: artifact.pinned ?? artifact.isPinned,
  });
};

export const normalizeInsightArtifacts = (artifacts = []) =>
  (Array.isArray(artifacts) ? artifacts : [])
    .map((artifact) => normalizeInsightArtifact(artifact))
    .filter(Boolean)
    .sort((left, right) => Number(right.pinned) - Number(left.pinned) || right.createdAt - left.createdAt);

export const updateInsightArtifact = (artifact, patch = {}) => {
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
