const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const MARKDOWN_FORMATTING_PATTERN = /[*_`>#]/g;

export const stripMarkdown = (value) =>
  normalizeText(value)
    .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(/!\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(MARKDOWN_FORMATTING_PATTERN, '')
    .replace(/\s+/g, ' ')
    .trim();

export const splitMarkdownBlocks = (value) =>
  String(value || '')
    .split(/\n{2,}/)
    .map((block) => normalizeText(block))
    .filter(Boolean);

const normalizePoint = (value) => {
  const rawText = normalizeText(value);
  if (!rawText) {
    return '';
  }

  return stripMarkdown(rawText.replace(/^[-*+]\s+/, '').replace(/^\d+[.)]\s+/, ''));
};

export const extractKeyPoints = (value, maxPoints = 4) => {
  const bulletMatches = String(value || '')
    .split('\n')
    .filter((line) => /^\s*(?:[-*+]|\d+[.)])\s+/.test(line))
    .map((line) => normalizePoint(line))
    .filter(Boolean);

  if (bulletMatches.length > 0) {
    return bulletMatches.slice(0, maxPoints);
  }

  return splitMarkdownBlocks(value)
    .slice(1)
    .map((block) => normalizePoint(block))
    .filter(Boolean)
    .slice(0, maxPoints);
};

export const extractSummarySentence = (value, fallback = '暂无摘要。', maxLength = 160) => {
  const blocks = splitMarkdownBlocks(value);
  const firstBlock = blocks[0] || fallback;
  const stripped = stripMarkdown(firstBlock);

  if (stripped.length <= maxLength) {
    return stripped;
  }

  return `${stripped.slice(0, maxLength).trimEnd()}...`;
};

export const buildInsightCardModel = ({
  content = '',
  summary = '',
  keyPoints = [],
  fallbackSummary = '暂无摘要。',
  maxPoints = 4,
  detailsTitle = '查看详情',
  defaultExpanded = false,
} = {}) => {
  const normalizedContent = normalizeText(content);
  const normalizedSummary = normalizeText(summary) || extractSummarySentence(normalizedContent, fallbackSummary);
  const normalizedPoints = (Array.isArray(keyPoints) ? keyPoints : [])
    .map((item) => normalizePoint(item))
    .filter(Boolean)
    .slice(0, maxPoints);
  const derivedPoints =
    normalizedPoints.length > 0 ? normalizedPoints : extractKeyPoints(normalizedContent, maxPoints);

  return {
    summary: normalizedSummary || fallbackSummary,
    points: derivedPoints,
    details: normalizedContent,
    hasDetails: Boolean(normalizedContent),
    hasPoints: derivedPoints.length > 0,
    detailsTitle,
    defaultExpanded,
  };
};
