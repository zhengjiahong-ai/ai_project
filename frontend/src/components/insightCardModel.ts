const normalizeText = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

const MARKDOWN_FORMATTING_PATTERN = /[*_`>#]/g;

export const stripMarkdown = (value: unknown): string =>
  normalizeText(value)
    .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(/!\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(MARKDOWN_FORMATTING_PATTERN, '')
    .replace(/\s+/g, ' ')
    .trim();

export const splitMarkdownBlocks = (value: unknown): string[] =>
  String(value || '')
    .split(/\n{2,}/)
    .map((block: string) => normalizeText(block))
    .filter(Boolean);

const normalizePoint = (value: unknown): string => {
  const rawText: string = normalizeText(value);
  if (!rawText) {
    return '';
  }

  return stripMarkdown(rawText.replace(/^[-*+]\s+/, '').replace(/^\d+[.)]\s+/, ''));
};

export const extractKeyPoints = (value: unknown, maxPoints: number = 4): string[] => {
  const bulletMatches: string[] = String(value || '')
    .split('\n')
    .filter((line: string) => /^\s*(?:[-*+]|\d+[.)])\s+/.test(line))
    .map((line: string) => normalizePoint(line))
    .filter(Boolean);

  if (bulletMatches.length > 0) {
    return bulletMatches.slice(0, maxPoints);
  }

  return splitMarkdownBlocks(value)
    .slice(1)
    .map((block: string) => normalizePoint(block))
    .filter(Boolean)
    .slice(0, maxPoints);
};

export const extractSummarySentence = (
  value: unknown,
  fallback: string = '暂无摘要。',
  maxLength: number = 160,
): string => {
  const blocks: string[] = splitMarkdownBlocks(value);
  const firstBlock: string = blocks[0] || fallback;
  const stripped: string = stripMarkdown(firstBlock);

  if (stripped.length <= maxLength) {
    return stripped;
  }

  return `${stripped.slice(0, maxLength).trimEnd()}...`;
};

export interface InsightCardModelInput {
  content?: string;
  summary?: string;
  keyPoints?: string[];
  fallbackSummary?: string;
  maxPoints?: number;
  detailsTitle?: string;
  defaultExpanded?: boolean;
}

export interface InsightCardModelOutput {
  summary: string;
  points: string[];
  details: string;
  hasDetails: boolean;
  hasPoints: boolean;
  detailsTitle: string;
  defaultExpanded: boolean;
}

export const buildInsightCardModel = ({
  content = '',
  summary = '',
  keyPoints = [],
  fallbackSummary = '暂无摘要。',
  maxPoints = 4,
  detailsTitle = '查看详情',
  defaultExpanded = false,
}: InsightCardModelInput = {}): InsightCardModelOutput => {
  const normalizedContent: string = normalizeText(content);
  const normalizedSummary: string = normalizeText(summary) || extractSummarySentence(normalizedContent, fallbackSummary);
  const normalizedPoints: string[] = (Array.isArray(keyPoints) ? keyPoints : [])
    .map((item: string) => normalizePoint(item))
    .filter(Boolean)
    .slice(0, maxPoints);
  const derivedPoints: string[] =
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
