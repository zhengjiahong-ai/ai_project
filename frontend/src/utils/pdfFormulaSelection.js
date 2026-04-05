const CJK_PATTERN = /[\u3400-\u9fff]/;
const SINGLE_LETTER_TOKEN_PATTERN = /\b[A-Za-z]\b/g;
const FORMULA_PUNCTUATION_PATTERN = /[=|{}()[\]^_\\]/;

const normalizeSpacing = (text) =>
  text
    .replace(/\s+/g, ' ')
    .replace(/\s*([{}()[\],=|+\-*/^_])\s*/g, '$1')
    .replace(/,\s*/g, ', ')
    .trim();

const looksLikeFlattenedFormula = (text) => {
  const normalized = String(text || '').trim();
  if (!normalized || CJK_PATTERN.test(normalized)) {
    return false;
  }

  const singleLetterCount = (normalized.match(SINGLE_LETTER_TOKEN_PATTERN) || []).length;
  return FORMULA_PUNCTUATION_PATTERN.test(normalized) || singleLetterCount >= 4;
};

const normalizeIndexedTokens = (text) => {
  let normalized = String(text || '').replace(/\s+/g, ' ').trim();

  normalized = normalized.replace(/\b([A-Za-z])\s+([A-Za-z])\s+([A-Za-z])\b/g, '$1_$2^$3');
  normalized = normalized.replace(/\b([A-Za-z])\s+([A-Za-z])\b/g, '$1_$2');
  normalized = normalizeSpacing(normalized);
  normalized = normalized.replace(/\[\s*([A-Za-z](?:_[A-Za-z0-9]+)?)\|\s*i\s*=\s*([0-9]+)\b/g, '_{i=$2}^{|$1|}');
  normalized = normalized.replace(/\}\[/g, '}_{');

  if (/_\{i=\d+\}\^\{\|[A-Za-z](?:_[A-Za-z0-9]+)?\|$/.test(normalized)) {
    normalized = `${normalized}}`;
  }

  return normalized;
};

const wrapFormulaForMarkdown = (text) => {
  const trimmed = text.trim();
  if (!trimmed || trimmed.startsWith('$') || trimmed.includes('\n')) {
    return trimmed;
  }
  return `$${trimmed}$`;
};

export const normalizePdfSelectionText = (rawText = '') => {
  const normalizedRaw = String(rawText || '').replace(/\s+/g, ' ').trim();
  if (!looksLikeFlattenedFormula(normalizedRaw)) {
    return {
      rawText: normalizedRaw,
      normalizedText: normalizedRaw,
      displayText: normalizedRaw,
      isFormulaLike: false,
    };
  }

  const normalizedFormula = normalizeIndexedTokens(normalizedRaw);

  return {
    rawText: normalizedRaw,
    normalizedText: normalizedFormula,
    displayText: wrapFormulaForMarkdown(normalizedFormula),
    isFormulaLike: true,
  };
};

export const buildExplainSelectionPayload = (rawText = '') => {
  const normalized = normalizePdfSelectionText(rawText);

  if (!normalized.isFormulaLike) {
    return {
      displayMessage: `请解释以下内容：\n> ${normalized.displayText}`,
      backendPrompt: `请解释以下内容：\n> ${normalized.normalizedText}`,
    };
  }

  return {
    displayMessage: `请解释以下内容：\n> ${normalized.displayText}`,
    backendPrompt: [
      '下面内容来自 PDF 选区，复制时可能丢失了上下标、分式、求和或绝对值符号。',
      '如果它明显是数学公式，请先将其恢复为标准数学记号或 Markdown LaTeX，再用中文解释。',
      '',
      '归一化后的选区：',
      `> ${normalized.displayText}`,
      '',
      '原始选区：',
      `> ${normalized.rawText}`,
    ].join('\n'),
  };
};
