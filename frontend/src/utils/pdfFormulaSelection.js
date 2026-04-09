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

  const wordTokens = normalized.match(/[A-Za-z]{3,}/g) || [];
  const singleLetterCount = (normalized.match(SINGLE_LETTER_TOKEN_PATTERN) || []).length;
  const hasStrongMathPattern =
    /[_^]\{?[^}\s]+\}?/.test(normalized) ||
    /\|\s*[A-Za-z](?:_[A-Za-z0-9]+)?\s*\|/.test(normalized) ||
    /[=][^=]/.test(normalized) ||
    /\([^)]+,[^)]+\)/.test(normalized);

  if (wordTokens.length >= 4) {
    return false;
  }

  return (
    (FORMULA_PUNCTUATION_PATTERN.test(normalized) && hasStrongMathPattern) ||
    (singleLetterCount >= 4 && wordTokens.length <= 2)
  );
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

  normalized = normalized.replace(
    /^\(([^()]+)\)\}\|([A-Za-z](?:_[A-Za-z0-9]+)?)\|i=([0-9]+),?$/,
    (_, pair, token, start) => `{(${pair})}_{i=${start}}^{|${token}|}`,
  );

  return normalized;
};

const normalizeCardinalityForDisplay = (text) =>
  String(text || '').replace(/\^\{\|([^}]+)\|\}/g, '^{\\lvert $1 \\rvert}');

const formatNormalizedFormulaForDisplay = (text) => {
  let formatted = String(text || '').trim();

  formatted = formatted.replace(
    /\{(\([^()]+\))\}(_\{[^}]+\})?(\^\{[^}]+\})?/g,
    (_, tuple, subscript = '', superscript = '') => `{\\left\\{${tuple}\\right\\}}${subscript}${superscript}`,
  );

  return normalizeCardinalityForDisplay(formatted);
};

const wrapFormulaForMarkdown = (text) => {
  const trimmed = formatNormalizedFormulaForDisplay(text).trim();
  if (!trimmed || trimmed.startsWith('$') || trimmed.includes('\n')) {
    return trimmed;
  }
  return `$$\n${trimmed}\n$$`;
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
  const displayMessage = normalized.isFormulaLike ? normalized.displayText : normalized.rawText;

  if (!normalized.isFormulaLike) {
    return {
      displayMessage,
      backendPrompt: [
        '请直接解释下面这段内容。',
        '不要添加客套话或铺垫，直接给出解释。',
        '',
        '内容：',
        `> ${normalized.normalizedText}`,
      ].join('\n'),
    };
  }

  return {
    displayMessage,
    backendPrompt: [
      '请直接解释下面这个数学公式，用中文回答。',
      '要求：',
      '- 直接进入解释，不要添加来源说明、恢复说明或其他铺垫',
      '- 不要描述公式恢复或归一化过程',
      '- 如果需要展示公式，直接使用 Markdown LaTeX',
      '- 如果公式中的符号可以逐项解释，就直接解释每个符号和整体含义',
      '',
      '标准公式：',
      `> ${normalized.displayText}`,
      '',
      '原始选区仅供消歧，不要在回答中复述：',
      `> ${normalized.rawText}`,
    ].join('\n'),
  };
};
