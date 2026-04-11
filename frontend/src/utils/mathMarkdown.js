const PROTECTED_SEGMENT_PATTERN = /(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g;
const PROTECTED_SEGMENT_FULL_PATTERN = /^(?:```[\s\S]*```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)$/;
const MATH_COMMAND_PATTERN =
  /\\(?:sum|frac|prod|int|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|sigma|pi|cdot|times|leq|geq|neq|approx|left|right|mathbb|mathbf|mathrm|operatorname|ell)\b/;
const SUBSCRIPT_PATTERN = /[A-Za-z][A-Za-z0-9]*_\{?[^}\s]+\}?/;
const SUPERSCRIPT_PATTERN = /[A-Za-z][A-Za-z0-9]*\^\{?[^}\s]+\}?/;
const SUB_OR_SUP_PATTERN = /(?:[A-Za-z][A-Za-z0-9]*|[|][A-Za-z][A-Za-z0-9|]*[|])(?:_\{?[^}\s]+\}?|\^\{?[^}\s]+\}?)+/;
const CJK_PATTERN = /[\u3400-\u9fff]/g;
const INLINE_MATH_BOUNDARY_PATTERN = /(^|[\s(:,])(\|?[A-Za-z][A-Za-z0-9|]*(?:_\{?[^}\s]+\}?|\^\{?[^}\s]+\}?)+\|?)(?=$|[\s).,;:])/gm;
const LITERAL_SET_PATTERN =
  /(^|[\s=+\-*/(:,[])\{([^{}]+)\}(?=(?:_\{[^}]+\})?(?:\^\{[^}]+\})?(?:$|[\s),.;:]))/g;
const PURE_MATH_LINE_PATTERN = /^[A-Za-z0-9\\{}()[\]|_^=+\-*/.,:;\s]+$/;
const COMPACT_FORMULA_SPAN_PATTERN =
  /((?:[A-Za-z][A-Za-z0-9]*\s*=\s*)?\{?\([A-Za-z0-9,.\s|_^\\-]+\)\}?(?:_\{[^}\n]+\})?(?:\^\{[^}\n]+\})?)/g;

const applyToUnprotectedSlices = (text, transformer) =>
  text
    .split(PROTECTED_SEGMENT_PATTERN)
    .map((segment) => (PROTECTED_SEGMENT_FULL_PATTERN.test(segment) ? segment : transformer(segment)))
    .join('');

const countMatches = (pattern, value) => (value.match(pattern) || []).length;

const normalizeLatexDelimiters = (text) =>
  text
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_, content) => `$$\n${content.trim()}\n$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, content) => `$${content.trim()}$`);

const escapeLiteralSetBraces = (text) =>
  text.replace(LITERAL_SET_PATTERN, (match, prefix, body) => `${prefix}\\{${body}\\}`);

const normalizeMathSegment = (segment) => {
  if (segment.startsWith('$$') && segment.endsWith('$$')) {
    return `$$${escapeLiteralSetBraces(segment.slice(2, -2))}$$`;
  }

  if (segment.startsWith('$') && segment.endsWith('$')) {
    return `$${escapeLiteralSetBraces(segment.slice(1, -1))}$`;
  }

  return segment;
};

const normalizeProtectedMathSegments = (text) =>
  text.replace(PROTECTED_SEGMENT_PATTERN, (segment) =>
    segment.startsWith('$') ? normalizeMathSegment(segment) : segment,
  );

const isLikelyMathExpression = (candidate) => {
  const text = String(candidate || '').trim();
  if (!text || text.length < 3 || text.length > 180) {
    return false;
  }

  if (MATH_COMMAND_PATTERN.test(text)) {
    return true;
  }

  const cjkCount = countMatches(CJK_PATTERN, text);
  if (cjkCount > 6) {
    return false;
  }

  if (SUB_OR_SUP_PATTERN.test(text)) {
    return true;
  }

  const hasAssignment = text.includes('=');
  const hasSubscript = SUBSCRIPT_PATTERN.test(text);
  const hasSuperscript = SUPERSCRIPT_PATTERN.test(text);
  const hasIndexedBounds = /[_^]\{[^}]+\}/.test(text);
  const hasMathBars = /\|[A-Za-z][A-Za-z0-9_^{|}]*\|/.test(text);

  return hasAssignment && (hasSubscript || hasSuperscript || hasIndexedBounds || hasMathBars);
};

const wrapInlineMath = (candidate) => `$${escapeLiteralSetBraces(candidate.trim())}$`;
const wrapDisplayMath = (candidate) => `$$\n${escapeLiteralSetBraces(candidate.trim())}\n$$`;

const wrapPureFormulaLines = (text) =>
  text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('-') || trimmed.startsWith('*')) {
        return line;
      }

      if (
        countMatches(CJK_PATTERN, trimmed) > 0 ||
        !PURE_MATH_LINE_PATTERN.test(trimmed) ||
        !isLikelyMathExpression(trimmed) ||
        /\b(?:and|are|is|was|were|the|this|that|these|those|available|given|sequence|set|client|task|data)\b/i.test(
          trimmed,
        )
      ) {
        return line;
      }

      return wrapDisplayMath(trimmed);
    })
    .join('\n');

const replaceWrappedCandidate = (candidate) => {
  const normalizedCandidate = candidate.trim();
  if (countMatches(CJK_PATTERN, normalizedCandidate) > 0) {
    return candidate;
  }

  return isLikelyMathExpression(normalizedCandidate) ? wrapInlineMath(normalizedCandidate) : candidate;
};

const wrapCompactFormulaSpans = (text) =>
  text.replace(COMPACT_FORMULA_SPAN_PATTERN, (candidate) => replaceWrappedCandidate(candidate));

const wrapCommandExpressions = (text) =>
  text.replace(
    /(^|[\s:,\u3001\u3002\uff0c\uff1a])((?:\\(?:sum|frac|prod|int|sqrt|alpha|beta|gamma|delta|theta|lambda|mu|sigma|pi|cdot|times|leq|geq|neq|approx|left|right|mathbb|mathbf|mathrm|operatorname|ell)[^`$\u3400-\u9fff\u3001\u3002\uff0c\uff1a,;:\n]*)+)/gm,
    (match, prefix, candidate) => `${prefix}${replaceWrappedCandidate(candidate.trim())}`,
  );

const wrapInlineIndexedTokens = (text) =>
  text.replace(INLINE_MATH_BOUNDARY_PATTERN, (match, prefix, candidate) => `${prefix}${wrapInlineMath(candidate.trim())}`);

export const preprocessMathMarkdown = (content = '') => {
  const text = typeof content === 'string' ? content : String(content ?? '');

  let output = normalizeLatexDelimiters(text);
  output = normalizeProtectedMathSegments(output);
  output = applyToUnprotectedSlices(output, wrapPureFormulaLines);
  output = applyToUnprotectedSlices(output, wrapCommandExpressions);
  output = applyToUnprotectedSlices(output, wrapCompactFormulaSpans);
  output = applyToUnprotectedSlices(output, wrapInlineIndexedTokens);
  return output;
};
