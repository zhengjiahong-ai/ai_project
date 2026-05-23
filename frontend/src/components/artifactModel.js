const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const normalizeStringList = (value) =>
  (Array.isArray(value) ? value : [])
    .map((item) => normalizeText(item))
    .filter(Boolean);

export const createInsightArtifact = ({
  artifactId,
  kind = 'insight',
  title = '',
  summary = '',
  content = '',
  sourceSelectionId = null,
  sourceMessageId = null,
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
